"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import settings


def db_path_from_url(url: str | None = None) -> Path:
    raw = url or settings.database_url
    if raw.startswith("sqlite:///"):
        return Path(raw.removeprefix("sqlite:///"))
    return Path(raw)


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or db_path_from_url()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: wait on lock instead of failing under concurrent writers
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_schema(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    migrations = sorted(
        (Path(__file__).parent / "migrations").glob("*.sql")
    )
    for sql_path in migrations:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.commit()
    if own:
        conn.close()


def init_schema_v2(conn: sqlite3.Connection | None = None) -> None:
    """Initialize chapter-first v2 schema set.

    v2 migrations intentionally live in a separate directory to allow
    phased cutover without altering legacy migration order.
    """
    own = conn is None
    conn = conn or connect()
    migrations = sorted((Path(__file__).parent / "migrations_v2").glob("*.sql"))
    for sql_path in migrations:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.commit()
    if own:
        conn.close()
