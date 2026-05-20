"""YouTube ingestion driver — extract transcript and ingest.

Supports both legacy and newer youtube-transcript-api calling styles.
"""

import re
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi

from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.models import SourceType

logger = get_logger(__name__)

_PREFERRED_TRANSCRIPT_LANGUAGES = ["en", "hi"]

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

    # Fetch transcript (support multiple youtube-transcript-api versions)
    try:
        transcript_list = None

        # Newer API style: instance + fetch()
        instance_fetch_error = None
        try:
            api = YouTubeTranscriptApi()
            if hasattr(api, "fetch"):
                transcript_list = api.fetch(
                    video_id,
                    languages=_PREFERRED_TRANSCRIPT_LANGUAGES,
                )
        except Exception as e:
            instance_fetch_error = e

        # Legacy API fallback: static get_transcript()
        if transcript_list is None:
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                transcript_list = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=_PREFERRED_TRANSCRIPT_LANGUAGES,
                )
            elif instance_fetch_error is not None:
                raise instance_fetch_error
            else:
                raise RuntimeError(
                    "youtube-transcript-api does not expose a supported transcript method"
                )
    except Exception as e:
        logger.error("YouTube transcript fetch failed", url=url, error=str(e))
        return {
            "error": f"Could not get transcript: {e}",
            "error_code": "NO_TRANSCRIPT",
        }

    if not transcript_list:
        return {"error": "Empty transcript", "error_code": "NO_TRANSCRIPT"}

    # Normalize transcript — join segments into flowing text
    def _segment_text(entry: Any) -> str:
        if isinstance(entry, dict):
            return str(entry.get("text", ""))
        # Object-like transcript snippets in newer library versions
        value = getattr(entry, "text", "")
        return str(value)

    text = " ".join(_segment_text(entry) for entry in transcript_list)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return {"error": "Empty transcript", "error_code": "NO_TRANSCRIPT"}

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
