"""Smoke tests — verify core imports and basic engine flow."""

import tempfile
import os

import pytest


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path):
    """Use a temporary directory for all data during tests."""
    os.environ["RAG_MCP_CHROMA_PATH"] = str(tmp_path / "chroma")
    os.environ["RAG_MCP_METADATA_DB_PATH"] = str(tmp_path / "metadata.db")
    yield tmp_path


def test_package_imports():
    """Verify the package can be imported."""
    import rag_mcp
    assert rag_mcp.__version__ == "0.1.0"


def test_config_loads():
    """Verify settings load from environment."""
    from rag_mcp.config import Settings
    s = Settings()
    assert s.chunk_size == 512
    assert s.chunk_overlap == 50


def test_models_create():
    """Verify core models can be instantiated."""
    from rag_mcp.models import Document, Chunk, SearchResult, SourceType
    doc = Document(source_type=SourceType.TEXT)
    assert doc.status.value == "processing"
    assert doc.id  # auto-generated


def test_chunker():
    """Test basic text chunking."""
    from rag_mcp.engine.chunker import Chunker
    chunker = Chunker(chunk_size=50, chunk_overlap=10)
    text = "Hello world. " * 20
    chunks = chunker.chunk(text, document_id="test-doc")
    assert len(chunks) > 1
    assert all(c.document_id == "test-doc" for c in chunks)
    assert all(c.text for c in chunks)


def test_metadata_store(tmp_data_dir):
    """Test metadata store CRUD operations."""
    from rag_mcp.engine.metadata_store import MetadataStore
    from rag_mcp.models import Document, DocumentStatus, SourceType

    store = MetadataStore()

    doc = Document(
        namespace="test",
        source_type=SourceType.TEXT,
        title="Test Doc",
    )
    store.save_document(doc)

    retrieved = store.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.title == "Test Doc"

    store.update_document_status(doc.id, DocumentStatus.INDEXED, chunk_count=5)
    updated = store.get_document(doc.id)
    assert updated.status == DocumentStatus.INDEXED
    assert updated.chunk_count == 5

    docs = store.list_documents(namespace="test")
    assert len(docs) == 1

    deleted = store.delete_document(doc.id)
    assert deleted is True
    assert store.get_document(doc.id) is None


def test_ssrf_validation():
    """Test SSRF protection blocks private IPs."""
    from rag_mcp.security.ssrf import validate_url, SSRFError

    # Should pass for public URLs
    validate_url("https://example.com")

    # Should block private IPs
    with pytest.raises(SSRFError):
        validate_url("http://192.168.1.1/secret")

    with pytest.raises(SSRFError):
        validate_url("http://127.0.0.1:6379/")

    # Should block non-HTTP schemes
    with pytest.raises(SSRFError):
        validate_url("file:///etc/passwd")

    with pytest.raises(SSRFError):
        validate_url("ftp://internal.server/data")


def test_upload_sessions(tmp_data_dir):
    """Test session token generation, validation, and expiration."""
    from rag_mcp.upload.sessions import SessionManager

    mgr = SessionManager()
    sess = mgr.create_session(namespace="test-ns", expiry_minutes=5)

    assert sess["session_id"]
    assert sess["token"]
    assert sess["namespace"] == "test-ns"

    # Validation should succeed
    assert mgr.validate_session(sess["session_id"], sess["token"]) is True

    # Bad token should fail
    assert mgr.validate_session(sess["session_id"], "invalid-token") is False

    # Non-existent session should fail
    assert mgr.validate_session("unknown-id", sess["token"]) is False


def test_upload_api_endpoints(tmp_data_dir):
    """Test FastAPI upload and status endpoints."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from rag_mcp.upload.router import router as upload_router, set_engine
    from rag_mcp.upload.sessions import SessionManager
    from rag_mcp.engine.rag_engine import RAGEngine

    engine = RAGEngine()
    set_engine(engine)

    app = FastAPI()
    app.include_router(upload_router)
    client = TestClient(app)

    mgr = SessionManager()
    sess = mgr.create_session(namespace="api-test", expiry_minutes=10)

    # 1. Test status route (valid)
    resp = client.get(f"/upload/{sess['session_id']}/status?token={sess['token']}")
    assert resp.status_code == 200
    assert resp.json()["namespace"] == "api-test"
    assert resp.json()["status"] == "pending"

    # 2. Test status route (invalid token)
    resp = client.get(f"/upload/{sess['session_id']}/status?token=wrong")
    assert resp.status_code == 400

    # 3. Test serving HTML UI (valid)
    resp = client.get(f"/upload/{sess['session_id']}?token={sess['token']}")
    assert resp.status_code == 200
    assert "Secure Document Ingestion" in resp.text

    # 4. Test serving HTML UI (invalid token)
    resp = client.get(f"/upload/{sess['session_id']}?token=wrong")
    assert resp.status_code == 400
    assert "Session Invalid or Expired" in resp.text

    # 5. Test file upload processing
    # Create a dummy text file to upload
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("FastAPI upload indexing is working nicely in integration tests.")
        dummy_path = f.name

    try:
        with open(dummy_path, "rb") as f:
            resp = client.post(
                f"/upload/{sess['session_id']}?token={sess['token']}",
                files={"files": (os.path.basename(dummy_path), f, "text/plain")},
                data={"tags": "test-api, integration"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["successful_count"] == 1
        assert data["results"][0]["status"] == "indexed"

        # Check in engine that document was actually indexed
        results = engine.search("FastAPI upload indexing", namespace="api-test")
        assert len(results) > 0
        assert "FastAPI upload" in results[0].text
    finally:
        os.remove(dummy_path)


def test_transport_routing(tmp_data_dir):
    """Test that streamable-http and sse transport apps can be created and mounted in FastAPI."""
    from fastapi import FastAPI
    from starlette.applications import Starlette
    from rag_mcp.mcp.server import create_mcp_server
    from rag_mcp.engine.rag_engine import RAGEngine

    engine = RAGEngine()
    mcp = create_mcp_server(engine)

    # Test "sse" transport app generation
    app_sse = FastAPI()
    sse_mcp_app = mcp.http_app(transport="sse")
    assert isinstance(sse_mcp_app, Starlette)
    app_sse.mount("/mcp", sse_mcp_app)

    # Test "streamable-http" transport app generation
    app_http = FastAPI()
    http_mcp_app = mcp.http_app(transport="streamable-http")
    assert isinstance(http_mcp_app, Starlette)
    app_http.mount("/mcp", http_mcp_app)


def test_metrics_endpoint(tmp_data_dir):
    """Test Prometheus metrics endpoint registration and response."""
    pytest.importorskip("prometheus_client")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from rag_mcp.config import settings
    from rag_mcp.log import get_logger
    from rag_mcp.main import register_http_metrics_middleware, register_metrics_endpoint

    app = FastAPI()
    logger = get_logger("test_metrics")

    @app.get("/health")
    async def health():
        return {"ok": True}

    original_enabled = settings.metrics_enabled
    original_path = settings.metrics_path
    original_require_auth = settings.metrics_require_auth
    original_bearer = settings.metrics_bearer_token
    original_allowed_cidrs = list(settings.metrics_allowed_cidrs)
    original_metrics_rps = settings.metrics_rate_limit_rps
    original_metrics_burst = settings.metrics_rate_limit_burst
    try:
        settings.metrics_enabled = True
        settings.metrics_path = "/metrics"
        settings.metrics_require_auth = False
        settings.metrics_bearer_token = ""
        settings.metrics_allowed_cidrs = ["127.0.0.1/32", "::1/128"]
        settings.metrics_rate_limit_rps = 1000.0
        settings.metrics_rate_limit_burst = 1000

        register_http_metrics_middleware(app, logger)
        register_metrics_endpoint(app, logger)
        client = TestClient(app)

        # Generate some traffic so custom app metrics are populated.
        health_resp = client.get("/health")
        assert health_resp.status_code == 200

        resp = client.get("/metrics")

        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        assert "Cache-Control" in resp.headers
        assert "# HELP" in resp.text or "# TYPE" in resp.text
        assert "rag_mcp_http_requests_total" in resp.text
        assert "rag_mcp_http_request_duration_seconds" in resp.text
        assert "rag_mcp_http_requests_in_flight" in resp.text
        assert "rag_mcp_http_exceptions_total" in resp.text
    finally:
        settings.metrics_enabled = original_enabled
        settings.metrics_path = original_path
        settings.metrics_require_auth = original_require_auth
        settings.metrics_bearer_token = original_bearer
        settings.metrics_allowed_cidrs = original_allowed_cidrs
        settings.metrics_rate_limit_rps = original_metrics_rps
        settings.metrics_rate_limit_burst = original_metrics_burst


def test_metrics_auth_and_cidr_enforced(tmp_data_dir):
    """Metrics endpoint should enforce bearer token and CIDR allowlist."""
    pytest.importorskip("prometheus_client")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from rag_mcp.config import settings
    from rag_mcp.log import get_logger
    from rag_mcp.main import register_http_metrics_middleware, register_metrics_endpoint

    app = FastAPI()
    logger = get_logger("test_metrics_auth")

    original_enabled = settings.metrics_enabled
    original_path = settings.metrics_path
    original_require_auth = settings.metrics_require_auth
    original_bearer = settings.metrics_bearer_token
    original_allowed_cidrs = list(settings.metrics_allowed_cidrs)
    original_metrics_rps = settings.metrics_rate_limit_rps
    original_metrics_burst = settings.metrics_rate_limit_burst

    try:
        settings.metrics_enabled = True
        settings.metrics_path = "/metrics"
        settings.metrics_require_auth = True
        settings.metrics_bearer_token = "test-secret-token"
        settings.metrics_allowed_cidrs = ["127.0.0.1/32", "::1/128"]
        settings.metrics_rate_limit_rps = 1000.0
        settings.metrics_rate_limit_burst = 1000

        register_http_metrics_middleware(app, logger)
        register_metrics_endpoint(app, logger)
        client = TestClient(app)

        unauth = client.get("/metrics")
        assert unauth.status_code == 401

        bad_token = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
        assert bad_token.status_code == 401

        ok = client.get("/metrics", headers={"Authorization": "Bearer test-secret-token"})
        assert ok.status_code == 200

        # Re-register on a new app with a disallowing CIDR policy to verify 403 branch.
        settings.metrics_allowed_cidrs = ["10.0.0.0/8"]
        app_blocked = FastAPI()
        register_metrics_endpoint(app_blocked, logger)
        blocked_client = TestClient(app_blocked)
        blocked = blocked_client.get("/metrics", headers={"Authorization": "Bearer test-secret-token"})
        assert blocked.status_code == 403
    finally:
        settings.metrics_enabled = original_enabled
        settings.metrics_path = original_path
        settings.metrics_require_auth = original_require_auth
        settings.metrics_bearer_token = original_bearer
        settings.metrics_allowed_cidrs = original_allowed_cidrs
        settings.metrics_rate_limit_rps = original_metrics_rps
        settings.metrics_rate_limit_burst = original_metrics_burst


def test_upload_too_many_files_limit(tmp_data_dir):
    """Upload endpoint should reject requests exceeding file count limit."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from rag_mcp.config import settings
    from rag_mcp.engine.rag_engine import RAGEngine
    from rag_mcp.upload.router import router as upload_router, set_engine
    from rag_mcp.upload.sessions import SessionManager

    app = FastAPI()
    app.include_router(upload_router)
    engine = RAGEngine()
    set_engine(engine)
    client = TestClient(app)

    mgr = SessionManager()
    sess = mgr.create_session(namespace="limit-test", expiry_minutes=10)

    original_max_files = settings.upload_max_files_per_request
    try:
        settings.upload_max_files_per_request = 1
        files = [
            ("files", ("a.txt", b"hello", "text/plain")),
            ("files", ("b.txt", b"world", "text/plain")),
        ]
        resp = client.post(
            f"/upload/{sess['session_id']}?token={sess['token']}",
            files=files,
            data={"tags": "limit"},
        )
        assert resp.status_code == 413
    finally:
        settings.upload_max_files_per_request = original_max_files
