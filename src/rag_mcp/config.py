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
    upload_max_files_per_request: int = 10
    upload_max_total_size_mb: int = 100
    upload_session_secret: str = "dev-insecure-change-me"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8080
    default_namespace: str = "default"
    transport: str = "http"  # "stdio", "streamable-http", "sse", or "http"
    trust_proxy_headers: bool = False
    trusted_proxy_cidrs: list[str] = ["127.0.0.1/32", "::1/128"]
    uvicorn_workers: int = 1
    uvicorn_limit_concurrency: int = 200
    uvicorn_limit_max_requests: int = 10000
    uvicorn_timeout_keep_alive: int = 5
    uvicorn_backlog: int = 2048

    # --- Logging ---
    log_level: str = "INFO"

    # --- Observability ---
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    metrics_require_auth: bool = True
    metrics_bearer_token: str = ""
    metrics_allowed_cidrs: list[str] = [
        "127.0.0.1/32",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    ]

    # --- Traffic Controls ---
    metrics_rate_limit_rps: float = 0.0667  # ~1 request/15s
    metrics_rate_limit_burst: int = 2
    upload_rate_limit_rpm: int = 10
    upload_rate_limit_burst: int = 20

    # --- Security ---
    allowed_upload_extensions: list[str] = [
        ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown",
    ]


# Singleton instance — import this throughout the app
settings = Settings()
