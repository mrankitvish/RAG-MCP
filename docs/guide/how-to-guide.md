# How-To Guide

## Upload a document (secure session flow)

1. Call tool `create_upload_session` from [`ingestion tools`](../../src/rag_mcp/mcp/tools/ingestion.py:7).
2. Open returned `upload_url` in browser.
3. Upload one or more supported files.
4. Poll `check_upload_status` for completion.

Failure behavior from [`handle_file_upload()`](../../src/rag_mcp/upload/router.py:142):

- invalid token/session -> `400`
- too many files / too large payload -> `413`
- parse failure -> file-level `failed` status in JSON

## Retrieve knowledge (compact)

Use `retrieve` from [`retrieval tools`](../../src/rag_mcp/mcp/tools/retrieval.py:6):

```json
{
  "name": "retrieve",
  "arguments": {
    "query": "Summarize onboarding steps",
    "namespace": "default",
    "top_k": 5
  }
}
```

## Retrieve with full sources

Use `retrieve_with_sources` to include citation fields (`document_id`, `source_type`, `source_url`, `chunk_index`).

## Tune `top_k`

- Start: `top_k=5`
- Increase to `10..20` for broader recall
- Reduce to `3` for tighter precision

## Namespace usage

- Ingest and retrieve within same `namespace`
- For scope checks, use `list_documents` and `search_documents` from [`management tools`](../../src/rag_mcp/mcp/tools/management.py:6)

## Debug empty results

1. Check ingestion state via `get_ingestion_status`
2. Verify namespace match
3. Rephrase query with target terminology
4. Increase `top_k`
5. Confirm document exists with `list_documents`

## Handle upload or parser issues

- Unsupported extension -> verify parser map in [`_PARSERS`](../../src/rag_mcp/ingestion/file.py:42)
- PDF parser import error -> install PDF extra
- DOCX parser import error -> install DOCX extra
- URL fetch blocked -> check SSRF guard in [`validate_url()`](../../src/rag_mcp/security/ssrf.py:37)

