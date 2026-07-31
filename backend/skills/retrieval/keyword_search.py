"""Keyword search via SQLite FTS5."""

from __future__ import annotations

import sqlite3

from backend.storage.repositories import ContentBlockRepository


def keyword_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    source_ids: list[str] | None = None,
    top_k: int = 20,
) -> list[dict]:
    repo = ContentBlockRepository(conn)
    return repo.search_fts(query, source_ids=source_ids, limit=top_k)
