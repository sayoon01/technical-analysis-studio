"""Project and source application services."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from backend.orchestration.source_pipeline import SourcePipeline
from backend.skills.ingestion.file_detector import guess_mime, is_supported
from backend.skills.retrieval.hybrid_search import hybrid_search
from backend.storage.file_store import FileStore
from backend.storage.repositories import (
    ContentBlockRepository,
    PageRepository,
    ProjectRepository,
    SourceRepository,
)


class ProjectService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.repo = ProjectRepository(conn)

    def create(self, name: str, description: str | None = None) -> dict:
        project_id = f"PRJ-{uuid.uuid4().hex[:10].upper()}"
        return self.repo.create(project_id, name, description)

    def get(self, project_id: str) -> dict:
        row = self.repo.get(project_id)
        if not row:
            raise KeyError(project_id)
        return row

    def list(self) -> list[dict]:
        return self.repo.list()

    def patch(self, project_id: str, **fields) -> dict:
        row = self.repo.patch(project_id, **fields)
        if not row:
            raise KeyError(project_id)
        return row


class SourceService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        file_store: FileStore | None = None,
    ) -> None:
        self.conn = conn
        self.file_store = file_store or FileStore()
        self.sources = SourceRepository(conn)
        self.pages = PageRepository(conn)
        self.blocks = ContentBlockRepository(conn)
        self.projects = ProjectRepository(conn)
        self.pipeline = SourcePipeline(conn, self.file_store)

    def upload(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        *,
        role: str = "EVIDENCE_SOURCE",
    ) -> dict:
        if not self.projects.get(project_id):
            raise KeyError(project_id)
        if not is_supported(filename):
            raise ValueError(f"Unsupported file type: {filename}")

        source_id, path = self.file_store.save_upload(project_id, filename, data)
        row = self.sources.create(
            {
                "source_id": source_id,
                "project_id": project_id,
                "filename": filename,
                "mime_type": guess_mime(filename),
                "role": role,
                "status": "UPLOADED",
                "storage_path": str(path),
            }
        )
        self.projects.update_stage(project_id, "INGESTING")
        return row

    def list(self, project_id: str) -> list[dict]:
        return self.sources.list_for_project(project_id)

    def get(self, source_id: str) -> dict:
        row = self.sources.get(source_id)
        if not row:
            raise KeyError(source_id)
        return row

    def set_role(self, source_id: str, role: str) -> dict:
        row = self.sources.update(source_id, role=role)
        if not row:
            raise KeyError(source_id)
        return row

    def process(self, source_id: str) -> dict:
        return self.pipeline.process_source(source_id)

    def get_page(self, source_id: str, page_number: int) -> dict:
        page = self.pages.get(source_id, page_number)
        if not page:
            raise KeyError(f"{source_id}:{page_number}")
        blocks = self.blocks.list_for_source(source_id, page_number)
        metrics = self._metrics_for_page(source_id, page_number)
        structure = self._structure_for_page(source_id, page_number)
        return {
            **page,
            "blocks": blocks,
            "metrics": metrics,
            "structure": structure,
            "text": "\n".join(
                b["text"] for b in blocks if b.get("block_type") != "IMAGE"
            ),
        }

    def list_pages(self, source_id: str) -> list[dict]:
        return self.pages.list_for_source(source_id)

    def search(
        self,
        project_id: str,
        query: str,
        *,
        source_ids: list[str] | None = None,
    ) -> list[dict]:
        return hybrid_search(self.conn, project_id, query, source_ids=source_ids)

    def _metrics_for_page(self, source_id: str, page_number: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM metric_facts
            WHERE source_id = ? AND page_number = ?
            """,
            (source_id, page_number),
        ).fetchall()
        return [dict(r) for r in rows]

    def _structure_for_page(self, source_id: str, page_number: int) -> list[dict]:
        try:
            rows = self.conn.execute(
                """
                SELECT fact_id, fact_kind, title, payload_json,
                       confidence, verification_status
                FROM structure_facts
                WHERE source_id = ? AND page_number = ?
                """,
                (source_id, page_number),
            ).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except Exception:
                item["payload"] = {}
            out.append(item)
        return out
