"""RAG-MCP entrypoint — starts the MCP server."""

import argparse
import threading
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute

from rag_mcp.log import setup_logging, get_logger
from rag_mcp.config import settings


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

    @app.get(metrics_path, include_in_schema=False)
    async def metrics():
        try:
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
            set_engine(engine)
            app.include_router(upload_router)
            register_metrics_endpoint(app, logger)
            if static_dir.exists():
                app.mount("/upload/static", StaticFiles(directory=str(static_dir)), name="upload_static")
            logger.info(f"FastAPI Upload UI server starting on {args.host}:{args.port}")
            uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

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

        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
