"""FastAPI router for file upload session UI and upload processing endpoints."""

import os
import shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rag_mcp.config import settings
from rag_mcp.engine.rag_engine import RAGEngine
from rag_mcp.log import get_logger
from rag_mcp.upload.sessions import SessionManager
from rag_mcp.ingestion.file import ingest_from_file

logger = get_logger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])
session_manager = SessionManager()

# Global engine reference (will be injected on server startup)
_engine: RAGEngine | None = None


def set_engine(engine: RAGEngine) -> None:
    global _engine
    _engine = engine


def get_engine() -> RAGEngine:
    if _engine is None:
        raise HTTPException(status_code=500, detail="RAG Engine not initialized")
    return _engine


# Serve static frontend folder if it exists
static_dir = Path(__file__).parent.parent.parent.parent / "upload-ui"


@router.get("/{session_id}", response_class=HTMLResponse)
async def serve_upload_ui(session_id: str, token: str = Query(...)):
    """Serve the sleek drag-and-drop HTML upload UI page if session is valid."""
    if not session_manager.validate_session(session_id, token):
        # Serve premium "Link Expired/Invalid" HTML
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Link Expired - RAG-MCP</title>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
                <style>
                    body {{
                        margin: 0;
                        background: radial-gradient(circle at center, #1e1e2e 0%, #0f0f16 100%);
                        color: #cdd6f4;
                        font-family: 'Outfit', sans-serif;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        overflow: hidden;
                    }}
                    .container {{
                        background: rgba(30, 30, 46, 0.45);
                        backdrop-filter: blur(16px);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        padding: 3rem;
                        border-radius: 24px;
                        text-align: center;
                        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
                        max-width: 480px;
                        width: 90%;
                    }}
                    h1 {{
                        font-weight: 600;
                        font-size: 2.2rem;
                        background: linear-gradient(135deg, #f38ba8, #eba0ac);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        margin-top: 0;
                    }}
                    p {{
                        color: #a6adc8;
                        font-size: 1.1rem;
                        line-height: 1.6;
                        margin-bottom: 2rem;
                    }}
                    .icon {{
                        font-size: 4rem;
                        margin-bottom: 1rem;
                        display: block;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <span class="icon">⚠️</span>
                    <h1>Session Invalid or Expired</h1>
                    <p>This secure upload link has expired (15-minute lifespan) or has an invalid token. Please ask your AI assistant to generate a new session upload link.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400
        )

    # If valid, serve the index.html from static folder
    index_file = static_dir / "index.html"
    if index_file.exists():
        html_content = index_file.read_text(encoding="utf-8")
        # Inject session_id and token dynamically for frontend JS use
        html_content = html_content.replace("{{SESSION_ID}}", session_id)
        html_content = html_content.replace("{{TOKEN}}", token)
        return HTMLResponse(content=html_content)

    return HTMLResponse(content="<h2>Upload UI Static files not found. Check repository layout.</h2>", status_code=404)


@router.get("/{session_id}/status")
async def get_session_status(session_id: str, token: str = Query(...)):
    """Retrieve session details, expiration, and destination namespace."""
    if not session_manager.validate_session(session_id, token):
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    details = session_manager.get_session_status(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "namespace": details["namespace"],
        "status": details["status"],
        "expires_at": details["expires_at"],
        "files_count": details["files_count"],
    }


@router.post("/{session_id}")
async def handle_file_upload(
    session_id: str,
    token: str = Query(...),
    files: List[UploadFile] = File(...),
    tags: str = Form(""),
    engine: RAGEngine = Depends(get_engine)
):
    """Process uploaded files, validate size/type, index into RAG vector store."""
    if not session_manager.validate_session(session_id, token):
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    namespace = session_manager.get_session_namespace(session_id)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Temporary directory for uploaded files
    temp_upload_dir = Path("./data/uploads") / session_id
    temp_upload_dir.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0

    for file in files:
        file_path = temp_upload_dir / file.filename
        try:
            # Stream write to file to keep memory footprint extremely small
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Ingest
            ingest_res = ingest_from_file(
                engine=engine,
                file_path=str(file_path),
                namespace=namespace,
                tags=tag_list,
            )

            if "error" in ingest_res:
                results.append({
                    "filename": file.filename,
                    "status": "failed",
                    "error": ingest_res["error"]
                })
            else:
                success_count += 1
                results.append({
                    "filename": file.filename,
                    "status": "indexed",
                    "document_id": ingest_res.get("document_id"),
                    "chunks": ingest_res.get("chunk_count")
                })

        except Exception as e:
            logger.error("Failed to process uploaded file", filename=file.filename, error=str(e))
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
        finally:
            # Clean up temp file
            if file_path.exists():
                os.remove(file_path)

    # Clean up temp directory
    try:
        shutil.rmtree(temp_upload_dir)
    except Exception:
        pass

    session_manager.complete_session(session_id, success_count, success=True)

    return JSONResponse({
        "session_id": session_id,
        "namespace": namespace,
        "results": results,
        "successful_count": success_count,
    })
