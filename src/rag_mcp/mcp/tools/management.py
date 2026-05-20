"""MCP management tools — list, delete, search documents, status."""

from rag_mcp.engine.rag_engine import RAGEngine


def register_management_tools(mcp, engine: RAGEngine):
    """Register all management tools on the MCP server."""

    @mcp.tool(
        description=(
            "List all indexed documents, optionally filtered by namespace or "
            "source type. Use this when the user wants to see what knowledge "
            "is stored."
        )
    )
    def list_documents(
        namespace: str = None,
        source_type: str = None,
        limit: int = 20,
    ) -> list[dict]:
        """List documents in the knowledge base."""
        docs = engine.list_documents(
            namespace=namespace, source_type=source_type, limit=limit,
        )
        return [
            {
                "id": d.id, "title": d.title,
                "source_type": d.source_type.value,
                "source_url": d.source_url,
                "chunk_count": d.chunk_count,
                "tags": d.tags,
                "namespace": d.namespace,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]

    @mcp.tool(
        description=(
            "Remove a document and all its chunks from the knowledge base. "
            "Use this when the user wants to delete specific knowledge."
        )
    )
    def delete_document(document_id: str) -> dict:
        """Delete a document by ID."""
        deleted = engine.delete_document(document_id)
        if deleted:
            return {"status": "deleted", "document_id": document_id}
        return {"status": "not_found", "document_id": document_id}

    @mcp.tool(
        description=(
            "Search documents by title, tags, source type, or namespace. "
            "This searches document metadata, not content. Use this to find "
            "specific documents before retrieving from them."
        )
    )
    def search_documents(
        query: str = None,
        tags: list[str] = None,
        source_type: str = None,
        namespace: str = None,
    ) -> list[dict]:
        """Search document metadata."""
        docs = engine.search_documents(
            query=query, tags=tags,
            source_type=source_type, namespace=namespace,
        )
        return [
            {"id": d.id, "title": d.title, "source_type": d.source_type.value,
             "tags": d.tags, "namespace": d.namespace}
            for d in docs
        ]

    @mcp.tool(
        description=(
            "Check the processing status of a document. Returns whether "
            "the document is still processing, indexed, or failed. "
            "Use this after ingestion to confirm completion."
        )
    )
    def get_ingestion_status(document_id: str) -> dict:
        """Get current ingestion status of a document."""
        doc = engine.get_document(document_id)
        if not doc:
            return {"status": "not_found", "document_id": document_id}
        return {
            "document_id": doc.id, "title": doc.title,
            "status": doc.status.value, "chunk_count": doc.chunk_count,
            "error_message": doc.error_message,
        }
