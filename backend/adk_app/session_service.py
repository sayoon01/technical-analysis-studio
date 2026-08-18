from __future__ import annotations

from pathlib import Path

from google.adk.sessions import DatabaseSessionService

from backend.config import settings


def adk_session_db_url() -> str:
    root = settings.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "adk_sessions.db"
    return f"sqlite+aiosqlite:///{db_path}"


def build_session_service() -> DatabaseSessionService:
    return DatabaseSessionService(adk_session_db_url())
