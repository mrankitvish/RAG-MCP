"""FastMCP server setup — registers all tools and resources."""

from fastmcp import FastMCP

from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.mcp.tools.ingestion import register_ingestion_tools
from rag_mcp.mcp.tools.management import register_management_tools
from rag_mcp.mcp.tools.retrieval import register_retrieval_tools

logger = get_logger(__name__)


def create_mcp_server(engine: RAGEngine) -> FastMCP:
    """Create and configure the FastMCP server with all tools.

    Args:
        engine: Shared RAGEngine instance.

    Returns:
        Configured FastMCP server ready to start.
    """
    mcp = FastMCP(
        name="rag-mcp",
        version="0.1.0",
    )

    # Register all tool groups
    register_ingestion_tools(mcp, engine)
    register_retrieval_tools(mcp, engine)
    register_management_tools(mcp, engine)

    # Register status resource
    @mcp.resource("rag-mcp://status")
    def server_status() -> dict:
        """Current state of the RAG-MCP knowledge base."""
        docs = engine.list_documents(limit=10000)
        namespaces = list({d.namespace for d in docs})
        total_chunks = sum(d.chunk_count for d in docs)
        return {
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "namespaces": namespaces,
            "embedding_model": engine.embedder._model.get_embedding_dimension(),
            "version": "0.1.0",
        }

    logger.info("MCP server created with all tools registered")
    return mcp
