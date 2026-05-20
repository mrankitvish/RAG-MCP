"""RAG-MCP entrypoint — starts the MCP server."""

import argparse
import hmac
import ipaddress
import time
import threading
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute

from rag_mcp.log import setup_logging, get_logger
from rag_mcp.config import settings


METRICS_ROUTE_TEMPLATE_UNKNOWN = "unknown"
HTTP_METRICS_MIDDLEWARE_REGISTERED = False


class TokenBucketLimiter:
    """Thread-safe token bucket limiter for basic abuse control."""

    def __init__(self, refill_rate_per_sec: float, capacity: int) -> None:
        self._rate = max(refill_rate_per_sec, 0.000001)
        self._capacity = max(capacity, 1)
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._state.get(key, (float(self._capacity), now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            if tokens < 1.0:
                self._state[key] = (tokens, now)
                return False
            self._state[key] = (tokens - 1.0, now)
            return True


def _parse_cidrs(values: list[str]) -> list[ipaddress._BaseNetwork]:
    networks: list[ipaddress._BaseNetwork] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _ip_in_networks(ip_text: str, networks: list[ipaddress._BaseNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def _get_client_ip(request: Request, trusted_proxy_networks: list[ipaddress._BaseNetwork]) -> str:
    direct_ip = request.client.host if request.client else ""
    if direct_ip == "testclient":
        direct_ip = "127.0.0.1"
    if not settings.trust_proxy_headers:
        return direct_ip

    if direct_ip and _ip_in_networks(direct_ip, trusted_proxy_networks):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            forwarded_ip = xff.split(",", 1)[0].strip()
            if forwarded_ip:
                return forwarded_ip
    return direct_ip


def _normalize_http_route(request: Request) -> str:
    """Return low-cardinality route template label for metrics."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return METRICS_ROUTE_TEMPLATE_UNKNOWN


def register_http_metrics_middleware(app: FastAPI, logger) -> None:
    """Register production-safe HTTP metrics middleware.

    Exported metrics:
    - rag_mcp_http_requests_total{method,route,status}
    - rag_mcp_http_request_duration_seconds{method,route,status}
    - rag_mcp_http_requests_in_flight
    - rag_mcp_http_exceptions_total{method,route,exception_type}
    """
    if not settings.metrics_enabled:
        return

    global HTTP_METRICS_MIDDLEWARE_REGISTERED
    if HTTP_METRICS_MIDDLEWARE_REGISTERED:
        logger.info("HTTP metrics middleware already registered; skipping duplicate registration")
        return

    metrics_path = settings.metrics_path.strip() or "/metrics"
    if not metrics_path.startswith("/"):
        metrics_path = f"/{metrics_path}"

    metrics_limiter = TokenBucketLimiter(
        refill_rate_per_sec=settings.metrics_rate_limit_rps,
        capacity=settings.metrics_rate_limit_burst,
    )
    upload_limiter = TokenBucketLimiter(
        refill_rate_per_sec=max(settings.upload_rate_limit_rpm, 1) / 60.0,
        capacity=settings.upload_rate_limit_burst,
    )
    trusted_proxy_networks = _parse_cidrs(settings.trusted_proxy_cidrs)

    from prometheus_client import Counter, Gauge, Histogram

    request_total = Counter(
        "rag_mcp_http_requests_total",
        "Total HTTP requests handled by RAG-MCP",
        ["method", "route", "status"],
    )
    request_duration = Histogram(
        "rag_mcp_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "route", "status"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    in_flight = Gauge(
        "rag_mcp_http_requests_in_flight",
        "Number of in-flight HTTP requests",
    )
    exception_total = Counter(
        "rag_mcp_http_exceptions_total",
        "Unhandled HTTP exceptions by type",
        ["method", "route", "exception_type"],
    )

    @app.middleware("http")
    async def http_metrics(request: Request, call_next):
        method = request.method
        route_label = _normalize_http_route(request)
        client_ip = _get_client_ip(request, trusted_proxy_networks) or "unknown"
        start = time.perf_counter()
        in_flight.inc()

        path = request.url.path
        if path == metrics_path:
            if not metrics_limiter.allow(f"metrics:{client_ip}"):
                return PlainTextResponse("rate_limited\n", status_code=429)

        if path.startswith("/upload"):
            if not upload_limiter.allow(f"upload:{client_ip}"):
                return PlainTextResponse("rate_limited\n", status_code=429)

        try:
            response = await call_next(request)
            status = str(response.status_code)
            elapsed = max(0.0, time.perf_counter() - start)
            request_total.labels(method=method, route=route_label, status=status).inc()
            request_duration.labels(method=method, route=route_label, status=status).observe(elapsed)
            return response
        except Exception as exc:
            elapsed = max(0.0, time.perf_counter() - start)
            exception_total.labels(
                method=method,
                route=route_label,
                exception_type=exc.__class__.__name__,
            ).inc()
            request_total.labels(method=method, route=route_label, status="500").inc()
            request_duration.labels(method=method, route=route_label, status="500").observe(elapsed)
            raise
        finally:
            in_flight.dec()

    logger.info("HTTP metrics middleware enabled")
    HTTP_METRICS_MIDDLEWARE_REGISTERED = True


def register_metrics_endpoint(app: FastAPI, logger) -> None:
    """Register Prometheus metrics endpoint on the provided FastAPI app.

    The endpoint is enabled by default and can be controlled via settings:
    - RAG_MCP_METRICS_ENABLED=true|false
    - RAG_MCP_METRICS_PATH=/metrics
    """
    if not settings.metrics_enabled:
        logger.info("Prometheus metrics endpoint disabled")
        return

    metrics_path = settings.metrics_path.strip() or "/metrics"
    if not metrics_path.startswith("/"):
        metrics_path = f"/{metrics_path}"
    allowed_networks = _parse_cidrs(settings.metrics_allowed_cidrs)
    trusted_proxy_networks = _parse_cidrs(settings.trusted_proxy_cidrs)

    @app.get(metrics_path, include_in_schema=False)
    async def metrics(request: Request):
        try:
            client_ip = _get_client_ip(request, trusted_proxy_networks)
            if allowed_networks and not _ip_in_networks(client_ip, allowed_networks):
                return PlainTextResponse("forbidden\n", status_code=403)

            if settings.metrics_require_auth:
                expected = settings.metrics_bearer_token
                if not expected:
                    logger.error("Metrics auth is enabled but bearer token is empty")
                    return PlainTextResponse("metrics_unavailable 1\n", status_code=503)

                auth = request.headers.get("authorization", "")
                if not auth.startswith("Bearer "):
                    return PlainTextResponse("unauthorized\n", status_code=401)

                presented = auth[7:].strip()
                if not hmac.compare_digest(presented, expected):
                    return PlainTextResponse("unauthorized\n", status_code=401)

            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            payload = generate_latest()
            return PlainTextResponse(
                content=payload.decode("utf-8"),
                media_type=CONTENT_TYPE_LATEST,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:
            logger.error("Failed to render Prometheus metrics", error=str(exc))
            return PlainTextResponse(
                content="metrics_unavailable 1\n",
                status_code=503,
                media_type="text/plain; charset=utf-8",
                headers={"Cache-Control": "no-store"},
            )

    logger.info(f"Prometheus metrics endpoint enabled at {metrics_path}")


def main():
    """Initialize and start the RAG-MCP server."""
    setup_logging()
    logger = get_logger("rag_mcp")
    logger.info("Starting RAG-MCP...")

    # Parse arguments
    parser = argparse.ArgumentParser(description="RAG-MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default=settings.transport,
        choices=["stdio", "streamable-http", "sse", "http"],
        help="MCP transport protocol (stdio, streamable-http, sse, or http)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=settings.host,
        help="Host to bind the HTTP/SSE server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help="Port to bind the HTTP/SSE server to",
    )
    args, _ = parser.parse_known_args()

    # Initialize the RAG engine (loads embedding model, creates DB)
    from rag_mcp.engine.rag_engine import RAGEngine
    engine = RAGEngine()

    # Create the MCP server
    from rag_mcp.mcp.server import create_mcp_server
    mcp = create_mcp_server(engine)

    from rag_mcp.upload.router import router as upload_router, set_engine, static_dir
    from fastapi.staticfiles import StaticFiles

    if args.transport == "stdio":
        # Spin up background co-resident FastAPI server for Upload UI
        def run_api():
            app = FastAPI(title="RAG-MCP API", version="0.1.0")
            register_http_metrics_middleware(app, logger)
            set_engine(engine)
            app.include_router(upload_router)
            register_metrics_endpoint(app, logger)
            if static_dir.exists():
                app.mount("/upload/static", StaticFiles(directory=str(static_dir)), name="upload_static")
            logger.info(f"FastAPI Upload UI server starting on {args.host}:{args.port}")
            uvicorn.run(
                app,
                host=args.host,
                port=args.port,
                log_level="warning",
                workers=settings.uvicorn_workers,
                limit_concurrency=settings.uvicorn_limit_concurrency,
                limit_max_requests=settings.uvicorn_limit_max_requests,
                timeout_keep_alive=settings.uvicorn_timeout_keep_alive,
                backlog=settings.uvicorn_backlog,
            )

        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()

        # Run stdio transport blocking on the main thread
        logger.info("RAG-MCP server starting on stdio transport")
        mcp.run(transport="stdio")
    else:
        from contextlib import asynccontextmanager

        # Create FastMCP ASGI apps for both transports
        mcp_app_http = mcp.http_app(transport="streamable-http", path="/")
        mcp_app_sse = mcp.http_app(transport="sse")

        # Combine lifespans to initialize task groups for both
        @asynccontextmanager
        async def combined_lifespan(app_instance):
            async with mcp_app_http.lifespan(app_instance):
                async with mcp_app_sse.lifespan(app_instance):
                    yield

        # Run a single unified FastAPI application incorporating both the Upload UI and MCP endpoints
        app = FastAPI(title="RAG-MCP API", version="0.1.0", lifespan=combined_lifespan)
        register_http_metrics_middleware(app, logger)
        set_engine(engine)
        app.include_router(upload_router)
        register_metrics_endpoint(app, logger)
        if static_dir.exists():
            app.mount("/upload/static", StaticFiles(directory=str(static_dir)), name="upload_static")
        
        # Explicit trailing slash redirects to prevent the root mount from swallowing them
        from fastapi.responses import RedirectResponse
        @app.get("/upload", include_in_schema=False)
        async def redirect_upload(): return RedirectResponse(url="/upload/")
        @app.get("/mcp", include_in_schema=False)
        async def redirect_mcp_get(request: Request):
            # Compatibility shim: some clients still open SSE on configured MCP URL.
            accept = request.headers.get("accept", "")
            if "text/event-stream" in accept:
                return RedirectResponse(url="/sse")
            return RedirectResponse(url="/mcp/")

        @app.post("/mcp", include_in_schema=False)
        async def redirect_mcp_post():
            return RedirectResponse(url="/mcp/")

        # Mount the FastMCP apps
        app.mount("/mcp", mcp_app_http)
        app.mount("/", mcp_app_sse)

        @app.on_event("startup")
        async def debug_dump_routes() -> None:
            """Log effective routing table to debug mount/handler precedence."""
            logger.info("==== Effective FastAPI routes/mounts ====")
            for route in app.router.routes:
                route_type = route.__class__.__name__
                path = getattr(route, "path", "<no-path>")

                if isinstance(route, APIRoute):
                    methods = ",".join(sorted(route.methods or []))
                    logger.info(f"route type={route_type} path={path} methods={methods} name={route.name}")
                else:
                    mounted_app = getattr(route, "app", None)
                    mounted_app_type = mounted_app.__class__.__name__ if mounted_app else "<none>"
                    logger.info(f"route type={route_type} path={path} app={mounted_app_type}")
            logger.info("==== End routes/mounts dump ====")

        logger.info(f"Starting unified RAG-MCP server on http://{args.host}:{args.port}")
        logger.info(f"Upload UI is available at http://{args.host}:{args.port}/upload")
        logger.info(f"Streamable-HTTP MCP endpoint is available at http://{args.host}:{args.port}/mcp")
        logger.info(f"SSE MCP endpoint is available at http://{args.host}:{args.port}/sse")

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
            workers=settings.uvicorn_workers,
            limit_concurrency=settings.uvicorn_limit_concurrency,
            limit_max_requests=settings.uvicorn_limit_max_requests,
            timeout_keep_alive=settings.uvicorn_timeout_keep_alive,
            backlog=settings.uvicorn_backlog,
        )


if __name__ == "__main__":
    main()
