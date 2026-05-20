"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """RAG-MCP configuration.

    All settings can be overridden via environment variables
    prefixed with RAG_MCP_ (e.g. RAG_MCP_EMBEDDING_MODEL).
    """

    model_config = {"env_prefix": "RAG_MCP_"}

    # --- Embedding ---
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- ChromaDB ---
    chroma_path: Path = Path("./data/chroma")

    # --- SQLite Metadata ---
    metadata_db_path: Path = Path("./data/metadata.db")

    # --- Chunking ---
    chunk_size: int = 512
    chunk_overlap: int = 50

    # --- Upload ---
    upload_max_size_mb: int = 50
    upload_session_expiry_minutes: int = 15

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8080
    default_namespace: str = "default"
    transport: str = "streamable-http"  # "stdio" or "streamable-http" or "sse"

    # --- Logging ---
    log_level: str = "INFO"

    # --- Security ---
    allowed_upload_extensions: list[str] = [
        ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown",
    ]


# Singleton instance — import this throughout the app
settings = Settings()
