"""Export application service."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.domain.enums import ProjectStage
from backend.orchestration.finalization_pipeline import FinalizationPipeline
from backend.storage.edition_repository import EditionRepository


class ExportService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.pipeline = FinalizationPipeline(conn)
        self.editions = EditionRepository(conn)

    def export_readiness(self, edition_id: str) -> dict:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        project = self.conn.execute(
            "SELECT * FROM projects WHERE project_id = ?",
            (edition["project_id"],),
        ).fetchone()
        sections = self.conn.execute(
            "SELECT section_id, status, content_markdown FROM sections WHERE edition_id = ?",
            (edition_id,),
        ).fetchall()
        open_blockers = self.conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM review_issues
            WHERE section_id IN (SELECT section_id FROM sections WHERE edition_id = ?)
              AND status = 'OPEN'
              AND severity IN ('CRITICAL', 'MAJOR')
            """,
            (edition_id,),
        ).fetchone()
        full_review = self.conn.execute(
            """
            SELECT decision
            FROM reviews
            WHERE section_id = ? AND reviewer_type = 'editorial_full_report'
            ORDER BY created_at DESC LIMIT 1
            """,
            (f"FULL-{edition_id}",),
        ).fetchone()
        bad_markers = 0
        marker_re = re.compile(r"<!--|P-INFRA-|P-PROB-|VISUAL_REQUEST|EVD-", re.I)
        for s in sections:
            if marker_re.search(s["content_markdown"] or ""):
                bad_markers += 1

        checks = {
            "edition_exists": True,
            "project_stage_ready": (project and project["stage"] in {ProjectStage.READY_FOR_EXPORT.value, ProjectStage.FINALIZING.value}),
            "section_review_passed": all((s["status"] or "").upper() == "PASSED" for s in sections) if sections else False,
            "open_blocking_issues": int((open_blockers or {"c": 0})["c"]),
            "full_report_review_passed": (full_review is not None and full_review["decision"] == "PASS"),
            "internal_marker_sections": bad_markers,
        }
        ready = (
            checks["project_stage_ready"]
            and checks["section_review_passed"]
            and checks["open_blocking_issues"] == 0
            and checks["full_report_review_passed"]
            and checks["internal_marker_sections"] == 0
        )
        return {
            "edition_id": edition_id,
            "ready": ready,
            "checks": checks,
        }

    def export_edition(self, edition_id: str) -> dict:
        readiness = self.export_readiness(edition_id)
        if not readiness["ready"]:
            raise ValueError(f"Export gate blocked: {readiness['checks']}")
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
