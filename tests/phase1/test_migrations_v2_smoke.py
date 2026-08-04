from __future__ import annotations

import sqlite3

from backend.storage.database import init_schema_v2


def test_init_schema_v2_creates_chapter_tables(tmp_path):
    db = tmp_path / "v2.db"
    conn = sqlite3.connect(str(db))
    try:
        init_schema_v2(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "report_strategies" in tables
    assert "chapter_blueprints" in tables
    assert "chapters" in tables
    assert "paragraphs" in tables
    assert "visual_specs" in tables
    assert "publication_documents" in tables
    assert "agent_runs" in tables
