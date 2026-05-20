"""MCP ingestion tools — ingest_text, ingest_url, ingest_youtube, ingest_file."""

from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.models import SourceType


def register_ingestion_tools(mcp, engine: RAGEngine):
    """Register all ingestion tools on the MCP server."""

    @mcp.tool(
        description=(
            "Store text content in the knowledge base for later retrieval. "
            "Use this when the user wants to remember information, save notes, "
            "or add knowledge from pasted text."
        )
    )
    def ingest_text(
        text: str,
        title: str = "Untitled",
        namespace: str = "default",
        tags: list[str] = [],
    ) -> dict:
        """Ingest raw text into the knowledge base."""
        result = engine.ingest(
            text=text,
            source_type=SourceType.TEXT,
            title=title,
            namespace=namespace,
            tags=tags,
        )
        return result.model_dump()

    @mcp.tool(
        description=(
            "Fetch and index a webpage for later retrieval. "
            "Use this when the user shares a URL and wants to search "
            "its content later."
        )
    )
    def ingest_url(
        url: str,
        namespace: str = "default",
        tags: list[str] = [],
    ) -> dict:
        """Fetch a webpage and ingest its content."""
        from rag_mcp.ingestion.url import ingest_from_url
        return ingest_from_url(engine, url, namespace, tags)

    @mcp.tool(
        description=(
            "Extract and index a YouTube video transcript for later retrieval. "
            "Use this when the user shares a YouTube link and wants to search "
            "what was said in the video."
        )
    )
    def ingest_youtube(
        url: str,
        namespace: str = "default",
    ) -> dict:
        """Extract YouTube transcript and ingest it."""
        from rag_mcp.ingestion.youtube import ingest_from_youtube
        return ingest_from_youtube(engine, url, namespace)

    @mcp.tool(
        description=(
            "Index a local file (PDF, DOCX, TXT, Markdown) into the knowledge base. "
            "Use this when the user wants to ingest a file from the local filesystem."
        )
    )
    def ingest_file(
        file_path: str,
        namespace: str = "default",
        tags: list[str] = [],
    ) -> dict:
        """Parse and ingest a local file."""
        from rag_mcp.ingestion.file import ingest_from_file
        return ingest_from_file(engine, file_path, namespace, tags)

    @mcp.tool(
        description=(
            "Generate a temporary upload link for files too large or complex to send directly through chat. "
            "Use this when the user wants to upload a PDF, DOCX, or other large documents. "
            "Returns a URL they can open in their browser to complete the secure upload."
        )
    )
    def create_upload_session(
        namespace: str = "default",
    ) -> dict:
        """Create a secure temporary file upload session."""
        from rag_mcp.upload.sessions import SessionManager
        session_mgr = SessionManager()
        sess = session_mgr.create_session(namespace)
        # Note: Port and host are configurable, default to http://localhost:8080
        upload_url = f"http://localhost:8080/upload/{sess['session_id']}?token={sess['token']}"
        return {
            "session_id": sess["session_id"],
            "upload_url": upload_url,
            "expires_in": "15m",
            "message": "Please share this link with the user to upload their documents.",
        }

    @mcp.tool(
        description=(
            "Check the processing and indexing status of files uploaded in an upload session. "
            "Use this to check whether the user's uploaded files are finished parsing and indexing."
        )
    )
    def check_upload_status(
        session_id: str,
    ) -> dict:
        """Retrieve details and file status for an upload session."""
        from rag_mcp.upload.sessions import SessionManager
        session_mgr = SessionManager()
        status = session_mgr.get_session_status(session_id)
        if not status:
            return {"error": "Upload session not found", "error_code": "SESSION_NOT_FOUND"}
        return status

