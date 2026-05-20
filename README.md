# RAG-MCP

`rag-mcp` is an MCP knowledge server for saving and retrieving memory across sessions.

## What you can do

- Ingest knowledge from text, URLs, YouTube, and files
- Retrieve relevant chunks with semantic search
- Get source-aware results when needed
- List/search/delete indexed documents
- Upload files through generated a web URL 

## Quick Start (Local)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e "[dev]"

export RAG_MCP_UPLOAD_SESSION_SECRET='replace-with-strong-secret'
python -m rag_mcp.main
```

Verify server:

```bash
curl -i http://127.0.0.1:8080/mcp
curl -i http://127.0.0.1:8080/sse
curl -i http://127.0.0.1:8080/metrics
```

## Quick Start (Docker)

```bash
docker compose up --build -d
docker compose ps
```

Container settings are loaded from [`.env`](.env.example).

## Key MCP Tools

- Ingest: `ingest_text`, `ingest_url`, `ingest_youtube`, `ingest_file`
- Retrieval: `retrieve`, `retrieve_with_sources`
- Management: `list_documents`, `search_documents`, `delete_document`, `get_ingestion_status`
- Upload flow: `create_upload_session`, `check_upload_status`

## Typical User Flow

1. Ingest content into a namespace.
2. Query with `retrieve` or `retrieve_with_sources`.
3. Use management tools to inspect and maintain stored knowledge.

## Documentation

- [System Architecture](docs/guide/system-architecture.md)
- [Quick Setup](docs/guide/quick-setup.md)
- [How-To Guide](docs/guide/how-to-guide.md)

## Common Config Files

- App settings: [`src/rag_mcp/config.py`](src/rag_mcp/config.py)
- Container build: [`Dockerfile`](Dockerfile)
- Compose runtime: [`docker-compose.yml`](docker-compose.yml)
