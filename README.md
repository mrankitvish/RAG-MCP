# RAG-MCP

## Universal Knowledge Ingestion & Retrieval Layer for MCP Clients

> **`docker run rag-mcp`** — give any AI client persistent memory, document retrieval, and semantic search.

---

### Quickstart

```bash
# Install
pip install -e .

# Run
rag-mcp
```

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "rag-mcp": {
      "command": "rag-mcp"
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `ingest_text` | Store text content for later retrieval |
| `ingest_url` | Fetch and index a webpage |
| `ingest_youtube` | Extract and index a YouTube transcript |
| `ingest_file` | Index a local file (PDF, DOCX, TXT, MD) |
| `retrieve` | Semantic search across knowledge |
| `retrieve_with_sources` | Search with full citations |
| `list_documents` | List indexed documents |
| `delete_document` | Remove a document |
| `search_documents` | Search by metadata |
| `get_ingestion_status` | Check processing status |

### Development

```bash
pip install -e ".[dev]"
pytest
```
