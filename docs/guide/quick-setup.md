# Quick Setup

## Prerequisites

- Python `>=3.11` per [`pyproject.toml`](../../pyproject.toml:11)
- Access to download embedding model (`all-MiniLM-L6-v2`) on first startup

## Local install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e "[dev]"
```

## Minimal env config

```bash
export RAG_MCP_HOST=127.0.0.1
export RAG_MCP_PORT=8080
export RAG_MCP_METRICS_ENABLED=true
export RAG_MCP_METRICS_REQUIRE_AUTH=false
export RAG_MCP_UPLOAD_SESSION_SECRET='replace-with-strong-secret'
```

Primary settings are defined in [`Settings`](../../src/rag_mcp/config.py:8).

## Run

```bash
. .venv/bin/activate
python -m rag_mcp.main
```

## Docker

```bash
docker compose up --build
```

Uses [`Dockerfile`](../../Dockerfile) and [`docker-compose.yml`](../../docker-compose.yml).

## Verify

```bash
curl -i http://127.0.0.1:8080/mcp
curl -i http://127.0.0.1:8080/sse
curl -i http://127.0.0.1:8080/metrics
```

