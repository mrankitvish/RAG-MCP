# RAG-MCP

Universal ingestion + retrieval memory layer exposed as an MCP server.

`rag-mcp` lets MCP clients store and retrieve knowledge from:

- raw text
- web pages
- YouTube transcripts
- local files (`.txt`, `.md`, `.pdf`, `.docx`, `.doc`)

Core runtime starts in [`main()`](src/rag_mcp/main.py:257) and wires FastMCP transports, upload routes, metrics, and the shared [`RAGEngine`](src/rag_mcp/engine/rag_engine.py:16).

---

## Features

- MCP tools for ingestion, retrieval, and document management from [`src/rag_mcp/mcp/tools/`](src/rag_mcp/mcp/tools)
- Hybrid transport support:
  - streamable HTTP (`/mcp`)
  - SSE (`/sse` + `/messages` flow)
- Upload UI session flow from [`src/rag_mcp/upload/router.py`](src/rag_mcp/upload/router.py)
- Vector storage in Chroma via [`VectorStore`](src/rag_mcp/engine/vector_store.py:11)
- Metadata persistence in SQLite via [`MetadataStore`](src/rag_mcp/engine/metadata_store.py:15)
- Prometheus metrics endpoint (`/metrics`) with request instrumentation in [`register_http_metrics_middleware()`](src/rag_mcp/main.py:99)

---

## Project Documentation

- [System Architecture](docs/guide/system-architecture.md)
- [Quick Setup](docs/guide/quick-setup.md)
- [How-To Guide](docs/guide/how-to-guide.md)

---

## Quick Start (Local)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e "[dev]"

export RAG_MCP_UPLOAD_SESSION_SECRET='replace-with-strong-secret'
python -m rag_mcp.main
```

Health checks:

```bash
curl -i http://127.0.0.1:8080/mcp
curl -i http://127.0.0.1:8080/sse
curl -i http://127.0.0.1:8080/metrics
```

---

## Docker / Compose

Build and run with [`docker-compose.yml`](docker-compose.yml):

```bash
docker compose up --build -d
docker compose ps
```

Runtime environment is loaded from [`.env`](.env).

Container image definition is in [`Dockerfile`](Dockerfile).

---

## Exposed MCP Capabilities

Tool registration happens in [`create_mcp_server()`](src/rag_mcp/mcp/server.py:14):

- Ingestion: `ingest_text`, `ingest_url`, `ingest_youtube`, `ingest_file`, `create_upload_session`, `check_upload_status`
- Retrieval: `retrieve`, `retrieve_with_sources`
- Management: `list_documents`, `delete_document`, `search_documents`, `get_ingestion_status`
- Resource: `rag-mcp://status`

---

## Important Runtime Config

Defined in [`Settings`](src/rag_mcp/config.py:8):

- server/transport: `RAG_MCP_HOST`, `RAG_MCP_PORT`, `RAG_MCP_TRANSPORT`
- data paths: `RAG_MCP_CHROMA_PATH`, `RAG_MCP_METADATA_DB_PATH`
- upload guards: `RAG_MCP_UPLOAD_MAX_SIZE_MB`, `RAG_MCP_UPLOAD_MAX_TOTAL_SIZE_MB`, `RAG_MCP_UPLOAD_MAX_FILES_PER_REQUEST`
- security: `RAG_MCP_UPLOAD_SESSION_SECRET`
- metrics: `RAG_MCP_METRICS_ENABLED`, `RAG_MCP_METRICS_PATH`, `RAG_MCP_METRICS_REQUIRE_AUTH`

---

## Source of Truth

- Runtime bootstrap: [`src/rag_mcp/main.py`](src/rag_mcp/main.py)
- Configuration: [`src/rag_mcp/config.py`](src/rag_mcp/config.py)
- Engine: [`src/rag_mcp/engine/rag_engine.py`](src/rag_mcp/engine/rag_engine.py)
- Upload flow: [`src/rag_mcp/upload/router.py`](src/rag_mcp/upload/router.py), [`src/rag_mcp/upload/sessions.py`](src/rag_mcp/upload/sessions.py)
- SSRF guard: [`src/rag_mcp/security/ssrf.py`](src/rag_mcp/security/ssrf.py)
- Packaging/build: [`pyproject.toml`](pyproject.toml), [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml)
