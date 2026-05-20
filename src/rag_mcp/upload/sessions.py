"""Upload session manager — issues and validates temporary file upload sessions."""

import hmac
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
import sqlite_utils

from rag_mcp.config import settings
from rag_mcp.log import get_logger

logger = get_logger(__name__)

_SECRET = b"rag-mcp-session-secret-salt-12345"


class SessionManager:
    """Manages upload sessions, persisting them to the SQLite metadata DB."""

    def __init__(self) -> None:
        import sqlite3
        db_path = str(settings.metadata_db_path)
        settings.metadata_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        self._db = sqlite_utils.Database(conn)
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the upload_sessions table if it doesn't exist."""
        if "upload_sessions" not in self._db.table_names():
            self._db["upload_sessions"].create(
                {
                    "id": str,
                    "namespace": str,
                    "token": str,
                    "expires_at": str,
                    "status": str,  # "pending", "completed", "failed"
                    "files_count": int,
                },
                pk="id",
            )

    def generate_token(self, session_id: str, expires_at: str) -> str:
        """Generate a secure signature/token for a session ID."""
        msg = f"{session_id}:{expires_at}".encode()
        return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()

    def create_session(self, namespace: str = "default", expiry_minutes: int = 15) -> dict:
        """Create a new temporary upload session.

        Args:
            namespace: Destination namespace for uploaded files.
            expiry_minutes: Lifespan of the upload link.

        Returns:
            dict containing session_id, token, expires_at, and namespace.
        """
        session_id = str(uuid.uuid4())
        expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        expires_at = expires_at_dt.isoformat()
        token = self.generate_token(session_id, expires_at)

        self._db["upload_sessions"].insert(
            {
                "id": session_id,
                "namespace": namespace,
                "token": token,
                "expires_at": expires_at,
                "status": "pending",
                "files_count": 0,
            }
        )
        logger.info("Created upload session", session_id=session_id, namespace=namespace, expires_at=expires_at)
        return {
            "session_id": session_id,
            "token": token,
            "expires_at": expires_at,
            "namespace": namespace,
        }

    def validate_session(self, session_id: str, token: str) -> bool:
        """Check if a session ID is valid, matches the token, and has not expired."""
        try:
            row = self._db["upload_sessions"].get(session_id)
        except sqlite_utils.db.NotFoundError:
            logger.warning("Session not found", session_id=session_id)
            return False

        # Validate token
        expected_token = self.generate_token(session_id, row["expires_at"])
        if not hmac.compare_digest(row["token"], token) or not hmac.compare_digest(expected_token, token):
            logger.warning("Session token mismatch", session_id=session_id)
            return False

        # Check expiry
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                logger.warning("Session expired", session_id=session_id, expires_at=row["expires_at"])
                return False
        except Exception as e:
            logger.error("Failed to parse session expiry", session_id=session_id, error=str(e))
            return False

        return True

    def get_session_namespace(self, session_id: str) -> str:
        """Retrieve the namespace assigned to the upload session."""
        try:
            row = self._db["upload_sessions"].get(session_id)
            return row["namespace"]
        except sqlite_utils.db.NotFoundError:
            return "default"

    def complete_session(self, session_id: str, files_count: int, success: bool = True) -> None:
        """Update session status upon files upload completion."""
        status = "completed" if success else "failed"
        self._db["upload_sessions"].update(
            session_id,
            {"status": status, "files_count": files_count}
        )
        logger.info("Upload session finished", session_id=session_id, status=status, files=files_count)

    def get_session_status(self, session_id: str) -> dict | None:
        """Get session details and status."""
        try:
            return self._db["upload_sessions"].get(session_id)
        except sqlite_utils.db.NotFoundError:
            return None
