"""YouTube ingestion driver — extract transcript and ingest."""

import re

from youtube_transcript_api import YouTubeTranscriptApi

from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.models import SourceType

logger = get_logger(__name__)

_YT_PATTERNS = [
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
]


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    for pattern in _YT_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def ingest_from_youtube(
    engine: RAGEngine,
    url: str,
    namespace: str = "default",
) -> dict:
    """Extract YouTube transcript and ingest into the knowledge base.

    Returns:
        dict with document_id, chunk_count, title, and message.
    """
    video_id = _extract_video_id(url)
    if not video_id:
        return {
            "error": "Could not extract YouTube video ID from URL",
            "error_code": "PARSE_ERROR",
        }

    # Fetch transcript
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as e:
        logger.error("YouTube transcript fetch failed", url=url, error=str(e))
        return {
            "error": f"Could not get transcript: {e}",
            "error_code": "NO_TRANSCRIPT",
        }

    if not transcript_list:
        return {"error": "Empty transcript", "error_code": "NO_TRANSCRIPT"}

    # Normalize transcript — join segments into flowing text
    text = " ".join(entry["text"] for entry in transcript_list)
    text = re.sub(r"\s+", " ", text).strip()

    title = f"YouTube: {video_id}"

    # Ingest
    result = engine.ingest(
        text=text,
        source_type=SourceType.YOUTUBE,
        title=title,
        namespace=namespace,
        source_url=url,
    )
    return result.model_dump()
