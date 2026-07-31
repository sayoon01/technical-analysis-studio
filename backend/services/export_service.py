"""Export application service."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.orchestration.finalization_pipeline import FinalizationPipeline
from backend.storage.edition_repository import EditionRepository


class ExportService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.pipeline = FinalizationPipeline(conn)
        self.editions = EditionRepository(conn)

    def export_edition(self, edition_id: str) -> dict:
        if not self.editions.get(edition_id):
            raise KeyError(edition_id)
        return self.pipeline.run(edition_id)

    def list_exports(self, edition_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM exports WHERE edition_id = ?
            ORDER BY created_at DESC
            """,
            (edition_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_export(self, export_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM exports WHERE export_id = ?", (export_id,)
        ).fetchone()
        if not row:
            raise KeyError(export_id)
        return dict(row)

    def download_path(self, export_id: str) -> Path:
        row = self.get_export(export_id)
        path = Path(row["storage_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
