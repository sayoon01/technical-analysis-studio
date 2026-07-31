"""Repository access for projects, sources, pages, content blocks."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, project_id: str, name: str, description: str | None = None) -> dict:
        now = _now()
        self.conn.execute(
            """
            INSERT INTO projects (project_id, name, description, stage, created_at, updated_at)
            VALUES (?, ?, ?, 'CREATED', ?, ?)
            """,
            (project_id, name, description, now, now),
        )
        self.conn.commit()
        return self.get(project_id)

    def get(self, project_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_stage(self, project_id: str, stage: str) -> None:
        self.conn.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE project_id = ?",
            (stage, _now(), project_id),
        )
        self.conn.commit()

    def patch(self, project_id: str, **fields: Any) -> dict | None:
        allowed = {"name", "description", "stage", "current_edition_id", "resume_target_stage"}
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k in allowed and v is not None:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return self.get(project_id)
        sets.append("updated_at = ?")
        vals.append(_now())
        vals.append(project_id)
        self.conn.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE project_id = ?",
            vals,
        )
        self.conn.commit()
        return self.get(project_id)


class SourceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, row: dict) -> dict:
        self.conn.execute(
            """
            INSERT INTO sources (
                source_id, project_id, filename, mime_type, role, status,
                page_count, storage_path, ocr_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["source_id"],
                row["project_id"],
                row["filename"],
                row.get("mime_type"),
                row.get("role", "EVIDENCE_SOURCE"),
                row.get("status", "UPLOADED"),
                row.get("page_count"),
                row.get("storage_path"),
                row.get("ocr_quality"),
                row.get("created_at", _now()),
            ),
        )
        self.conn.commit()
        return self.get(row["source_id"])

    def get(self, source_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, source_id: str, **fields: Any) -> dict | None:
        allowed = {
            "role",
            "status",
            "page_count",
            "storage_path",
            "ocr_quality",
            "mime_type",
            "filename",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return self.get(source_id)
        vals.append(source_id)
        self.conn.execute(
            f"UPDATE sources SET {', '.join(sets)} WHERE source_id = ?",
            vals,
        )
        self.conn.commit()
        return self.get(source_id)


class PageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, page: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO source_pages (
                page_id, source_id, page_number, page_type,
                text_layer_available, image_path, width, height
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, page_number) DO UPDATE SET
                page_type = excluded.page_type,
                text_layer_available = excluded.text_layer_available,
                image_path = excluded.image_path,
                width = excluded.width,
                height = excluded.height
            """,
            (
                page["page_id"],
                page["source_id"],
                page["page_number"],
                page["page_type"],
                1 if page.get("text_layer_available", True) else 0,
                page.get("image_path"),
                page.get("width"),
                page.get("height"),
            ),
        )
        self.conn.commit()

    def list_for_source(self, source_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM source_pages
            WHERE source_id = ?
            ORDER BY page_number
            """,
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, source_id: str, page_number: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM source_pages
            WHERE source_id = ? AND page_number = ?
            """,
            (source_id, page_number),
        ).fetchone()
        return dict(row) if row else None


class ContentBlockRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def delete_for_source(self, source_id: str) -> None:
        self.conn.execute(
            "DELETE FROM content_blocks_fts WHERE source_id = ?", (source_id,)
        )
        self.conn.execute(
            "DELETE FROM content_blocks WHERE source_id = ?", (source_id,)
        )
        self.conn.commit()

    def insert_many(self, blocks: list[dict]) -> None:
        for b in blocks:
            x0, y0, x1, y1 = b.get("bbox", (0.0, 0.0, 0.0, 0.0))
            self.conn.execute(
                """
                INSERT INTO content_blocks (
                    block_id, source_id, page_number, block_type, text,
                    bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                    reading_order, confidence, parent_section
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    b["block_id"],
                    b["source_id"],
                    b["page_number"],
                    b["block_type"],
                    b["text"],
                    x0,
                    y0,
                    x1,
                    y1,
                    b.get("reading_order", 0),
                    b.get("confidence", 0.0),
                    b.get("parent_section"),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO content_blocks_fts (block_id, source_id, page_number, text)
                VALUES (?, ?, ?, ?)
                """,
                (b["block_id"], b["source_id"], b["page_number"], b["text"]),
            )
        self.conn.commit()

    def list_for_source(self, source_id: str, page_number: int | None = None) -> list[dict]:
        if page_number is None:
            rows = self.conn.execute(
                """
                SELECT * FROM content_blocks
                WHERE source_id = ?
                ORDER BY page_number, reading_order
                """,
                (source_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM content_blocks
                WHERE source_id = ? AND page_number = ?
                ORDER BY reading_order
                """,
                (source_id, page_number),
            ).fetchall()
        return [self._to_block(r) for r in rows]

    def search_fts(
        self,
        query: str,
        *,
        source_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        # Escape FTS special chars loosely; quote tokens
        tokens = [t for t in query.replace('"', " ").split() if t]
        if not tokens:
            return []
        fts_q = " ".join(f'"{t}"' for t in tokens)
        sql = """
            SELECT b.*
            FROM content_blocks_fts f
            JOIN content_blocks b ON b.block_id = f.block_id
            WHERE content_blocks_fts MATCH ?
        """
        params: list[Any] = [fts_q]
        if source_ids:
            placeholders = ",".join("?" * len(source_ids))
            sql += f" AND b.source_id IN ({placeholders})"
            params.extend(source_ids)
        sql += " LIMIT ?"
        params.append(limit)
        # MATCH uses the fts table name in FROM
        sql = """
            SELECT b.*
            FROM content_blocks_fts
            JOIN content_blocks b ON b.block_id = content_blocks_fts.block_id
            WHERE content_blocks_fts MATCH ?
        """
        params = [fts_q]
        if source_ids:
            placeholders = ",".join("?" * len(source_ids))
            sql += f" AND b.source_id IN ({placeholders})"
            params.extend(source_ids)
        sql += " LIMIT ?"
        params.append(limit)
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Fallback: LIKE search if FTS query fails
            like = f"%{query}%"
            rows = self.conn.execute(
                """
                SELECT * FROM content_blocks
                WHERE text LIKE ?
                ORDER BY page_number, reading_order
                LIMIT ?
                """,
                (like, limit),
            ).fetchall()
        return [self._to_block(r) for r in rows]

    @staticmethod
    def _to_block(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["bbox"] = (
            d.pop("bbox_x0", 0.0) or 0.0,
            d.pop("bbox_y0", 0.0) or 0.0,
            d.pop("bbox_x1", 0.0) or 0.0,
            d.pop("bbox_y1", 0.0) or 0.0,
        )
        return d
