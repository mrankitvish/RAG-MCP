FROM python:3.11-slim AS base

WORKDIR /app

# System deps for PDF parsing (optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Pre-download the default embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy source and static UI files
COPY src/ ./src/
COPY upload-ui/ ./upload-ui/

# Data persistence volume
VOLUME ["/data"]

ENV RAG_MCP_CHROMA_PATH=/data/chroma
ENV RAG_MCP_METADATA_DB_PATH=/data/metadata.db
ENV RAG_MCP_LOG_LEVEL=INFO

EXPOSE 8080

ENTRYPOINT ["python", "-m", "rag_mcp.main"]
