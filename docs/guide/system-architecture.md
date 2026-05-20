# System Architecture

## Overview

`rag-mcp` runs a unified FastAPI app that mounts:

- Streamable HTTP MCP transport at `/mcp`
- SSE MCP transport at `/` with `/sse` handshake path
- Upload routes under `/upload`
- Metrics at configurable `metrics_path` (default `/metrics`)

Runtime wiring is implemented in [`main()`](../../src/rag_mcp/main.py:257).

## High-Level Diagram

```mermaid
flowchart LR
    A[MCP Client] -->|/mcp| B[FastAPI]
    A -->|/sse + /messages| B
    U[Upload Browser UI] -->|/upload| B
    B --> T[FastMCP Tools]
    T --> E[RAGEngine]
    E --> C[ChromaDB VectorStore]
    E --> S[SQLite MetadataStore]
    B --> M[/metrics]
```

## Component Diagram

```mermaid
flowchart TD
    MAIN[main.py] --> METRIC_MW[HTTP metrics middleware]
    MAIN --> METRIC_EP[/metrics endpoint]
    MAIN --> UPLOAD[upload router]
    MAIN --> MCP_APPS[FastMCP mounted apps]

    MCP_APPS --> TOOLS[ingestion/retrieval/management tools]
    TOOLS --> ENGINE[RAGEngine]
    ENGINE --> CHUNKER[Chunker]
    ENGINE --> EMBEDDER[Embedder]
    ENGINE --> VECTOR[VectorStore]
    ENGINE --> META[MetadataStore]
```

## Request Flow

1. Request enters FastAPI
2. Middleware in [`register_http_metrics_middleware()`](../../src/rag_mcp/main.py:99)
3. Route handler or mounted FastMCP transport handles request
4. Tool path calls engine (`ingest`, `search`, `list`, `delete`)
5. Response emitted; metrics updated

## Data Path

- Ingestion: parser -> [`RAGEngine.ingest()`](../../src/rag_mcp/engine/rag_engine.py:27) -> chunk -> embed -> vector upsert -> metadata/chunk save
- Retrieval: query embed -> vector query -> similarity mapping -> tool response

