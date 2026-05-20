"""RAG-MCP entrypoint — starts the MCP server."""

import argparse
import threading
import uvicorn
from fastapi import FastAPI

from rag_mcp.log import setup_logging, get_logger
from rag_mcp.config import settings


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
        choices=["stdio", "streamable-http", "sse"],
        help="MCP transport protocol (stdio, streamable-http, or sse)",
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

    from rag_mcp.upload.router import router as upload_router, set_engine

    if args.transport == "stdio":
        # Spin up background co-resident FastAPI server for Upload UI
        def run_api():
            app = FastAPI(title="RAG-MCP API", version="0.1.0")
            set_engine(engine)
            app.include_router(upload_router)
            logger.info(f"FastAPI Upload UI server starting on {args.host}:{args.port}")
            uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()

        # Run stdio transport blocking on the main thread
        logger.info("RAG-MCP server starting on stdio transport")
        mcp.run(transport="stdio")
    else:
        # Run a single unified FastAPI application incorporating both the Upload UI and MCP endpoints
        app = FastAPI(title="RAG-MCP API", version="0.1.0")
        set_engine(engine)
        app.include_router(upload_router)

        # Create FastMCP ASGI app and mount under "/mcp"
        mcp_app = mcp.http_app(transport=args.transport)
        app.mount("/mcp", mcp_app)

        logger.info(
            f"Starting unified RAG-MCP server with transport {args.transport!r} on http://{args.host}:{args.port}"
        )
        logger.info(f"Upload UI is available at http://{args.host}:{args.port}/upload")
        logger.info(f"MCP endpoint is available at http://{args.host}:{args.port}/mcp")

        uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
