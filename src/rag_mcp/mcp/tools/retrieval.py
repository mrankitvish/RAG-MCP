"""MCP retrieval tools — retrieve, retrieve_with_sources."""

from rag_mcp.engine.rag_engine import RAGEngine


def register_retrieval_tools(mcp, engine: RAGEngine):
    """Register all retrieval tools on the MCP server."""

    @mcp.tool(
        description=(
            "Search the knowledge base using semantic similarity. "
            "Use this when the user asks a question that might be answered "
            "by previously stored knowledge. Returns the most relevant "
            "text chunks."
        )
    )
    def retrieve(
        query: str,
        namespace: str = "default",
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search across ingested knowledge."""
        results = engine.search(query, namespace=namespace, top_k=top_k)
        return [
            {
                "text": r.text,
                "score": r.score,
                "title": r.document_title,
                "source": r.source_url or r.source_type,
            }
            for r in results
        ]

    @mcp.tool(
        description=(
            "Search the knowledge base with full source citations for "
            "verifiable answers. Returns text chunks along with document ID, "
            "source URL, source type, and chunk index."
        )
    )
    def retrieve_with_sources(
        query: str,
        namespace: str = "default",
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search with full citation metadata."""
        results = engine.search(query, namespace=namespace, top_k=top_k)
        return [r.model_dump() for r in results]
