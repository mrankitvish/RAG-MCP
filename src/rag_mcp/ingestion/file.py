"""File ingestion driver — parse local files and ingest."""

from pathlib import Path

from rag_mcp.config import settings
from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.models import SourceType

logger = get_logger(__name__)


def _read_text_file(path: Path) -> str:
    """Read a plain text or markdown file."""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF file using unstructured."""
    try:
        from unstructured.partition.pdf import partition_pdf
        elements = partition_pdf(str(path))
        return "\n\n".join(str(el) for el in elements)
    except ImportError:
        raise ImportError(
            "PDF support requires the 'pdf' extra: pip install rag-mcp[pdf]"
        )


def _read_docx(path: Path) -> str:
    """Extract text from a DOCX file."""
    try:
        import docx
        doc = docx.Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise ImportError(
            "DOCX support requires the 'docx' extra: pip install rag-mcp[docx]"
        )


_PARSERS = {
    ".txt": _read_text_file,
    ".md": _read_text_file,
    ".markdown": _read_text_file,
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".doc": _read_docx,
}


def ingest_from_file(
    engine: RAGEngine,
    file_path: str,
    namespace: str = "default",
    tags: list[str] | None = None,
) -> dict:
    """Parse a local file and ingest into the knowledge base.

    Returns:
        dict with document_id, chunk_count, title, and message.
    """
    path = Path(file_path)

    if not path.exists():
        return {"error": f"File not found: {file_path}", "error_code": "FILE_NOT_FOUND"}

    if not path.is_file():
        return {"error": f"Not a file: {file_path}", "error_code": "FILE_NOT_FOUND"}

    ext = path.suffix.lower()
    if ext not in _PARSERS:
        supported = ", ".join(_PARSERS.keys())
        return {
            "error": f"Unsupported file type: {ext}. Supported: {supported}",
            "error_code": "PARSE_ERROR",
        }

    # Check file size
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > settings.upload_max_size_mb:
        return {
            "error": f"File too large: {size_mb:.1f}MB (max {settings.upload_max_size_mb}MB)",
            "error_code": "PARSE_ERROR",
        }

    # Parse
    try:
        text = _PARSERS[ext](path)
    except Exception as e:
        logger.error("File parsing failed", path=str(path), error=str(e))
        return {"error": f"Failed to parse file: {e}", "error_code": "PARSE_ERROR"}

    if not text.strip():
        return {"error": "No text content extracted from file", "error_code": "PARSE_ERROR"}

    # Ingest
    result = engine.ingest(
        text=text,
        source_type=SourceType.FILE,
        title=path.stem,
        namespace=namespace,
        filename=path.name,
        tags=tags or [],
    )
    return result.model_dump()
