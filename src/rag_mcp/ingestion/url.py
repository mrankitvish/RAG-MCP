"""URL ingestion driver — fetch, clean, and ingest web pages."""

import httpx
from bs4 import BeautifulSoup

from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.models import SourceType
from rag_mcp.security.ssrf import SSRFError, validate_url

logger = get_logger(__name__)

_TIMEOUT = 30.0
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10MB


def ingest_from_url(
    engine: RAGEngine,
    url: str,
    namespace: str = "default",
    tags: list[str] | None = None,
) -> dict:
    """Fetch a URL, extract text, and ingest into the knowledge base.

    Returns:
        dict with document_id, chunk_count, title, and message.
    """
    # SSRF validation
    try:
        validate_url(url)
    except SSRFError as e:
        return {"error": str(e), "error_code": "SSRF_BLOCKED"}

    # Fetch page
    try:
        resp = httpx.get(
            url,
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "RAG-MCP/0.1"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("URL fetch failed", url=url, error=str(e))
        return {"error": f"Failed to fetch URL: {e}", "error_code": "FETCH_FAILED"}

    if len(resp.content) > _MAX_RESPONSE_BYTES:
        return {"error": "Response too large (>10MB)", "error_code": "FETCH_FAILED"}

    # Parse HTML and extract text
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = soup.get_text(separator="\n", strip=True)

    if not text.strip():
        return {"error": "No text content found on page", "error_code": "PARSE_ERROR"}

    # Ingest
    result = engine.ingest(
        text=text,
        source_type=SourceType.URL,
        title=title,
        namespace=namespace,
        source_url=url,
        tags=tags or [],
    )
    return result.model_dump()
