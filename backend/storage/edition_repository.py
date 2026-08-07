"""Edition / section / claim persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.domain.chapter import ChapterDraft


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EditionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def next_edition_number(self, project_id: str) -> int:
        row = self.conn.execute(
            "SELECT MAX(edition_number) AS m FROM report_editions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["m"] or 0) + 1

    def create_snapshot(self, project_id: str, source_ids: list[str]) -> str:
        row = self.conn.execute(
            "SELECT MAX(snapshot_number) AS m FROM corpus_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        num = int(row["m"] or 0) + 1
        snapshot_id = f"SNP-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO corpus_snapshots (snapshot_id, project_id, snapshot_number, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot_id, project_id, num, _now()),
        )
        for sid in source_ids:
            self.conn.execute(
                """
                INSERT INTO corpus_snapshot_sources (snapshot_id, source_id)
                VALUES (?, ?)
                """,
                (snapshot_id, sid),
            )
        self.conn.commit()
        return snapshot_id

    def create_edition(
        self,
        *,
        project_id: str,
        corpus_snapshot_id: str,
        report_plan_id: str,
        outline_id: str,
        parent_edition_id: str | None = None,
    ) -> dict:
        edition_id = f"ED-{uuid.uuid4().hex[:10].upper()}"
        num = self.next_edition_number(project_id)
        self.conn.execute(
            """
            INSERT INTO report_editions (
                edition_id, project_id, edition_number, parent_edition_id,
                corpus_snapshot_id, report_plan_id, outline_id, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PRODUCING', ?)
            """,
            (
                edition_id,
                project_id,
                num,
                parent_edition_id,
                corpus_snapshot_id,
                report_plan_id,
                outline_id,
                _now(),
            ),
        )
        self.conn.commit()
        return self.get(edition_id)

    def get(self, edition_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM report_editions WHERE edition_id = ?", (edition_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM report_editions
            WHERE project_id = ?
            ORDER BY edition_number
            """,
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, edition_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE report_editions SET status = ? WHERE edition_id = ?",
            (status, edition_id),
        )
        self.conn.commit()


class SectionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, row: dict) -> dict:
        self.conn.execute(
            """
            INSERT INTO sections (
                section_id, edition_id, outline_node_id, title, objective,
                content_markdown, status, revision_count, evidence_pack_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["section_id"],
                row["edition_id"],
                row["outline_node_id"],
                row["title"],
                row.get("objective"),
                row.get("content_markdown", ""),
                row.get("status", "PENDING"),
                row.get("revision_count", 0),
                row.get("evidence_pack_id"),
                _now(),
            ),
        )
        self.conn.commit()
        return self.get(row["section_id"])

    def get(self, section_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM sections WHERE section_id = ?", (section_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_for_edition(self, edition_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM sections WHERE edition_id = ?
            ORDER BY rowid
            """,
            (edition_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, section_id: str, **fields: Any) -> dict | None:
        allowed = {
            "content_markdown",
            "status",
            "revision_count",
            "evidence_pack_id",
            "title",
            "objective",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return self.get(section_id)
        sets.append("updated_at = ?")
        vals.append(_now())
        vals.append(section_id)
        self.conn.execute(
            f"UPDATE sections SET {', '.join(sets)} WHERE section_id = ?",
            vals,
        )
        self.conn.commit()
        return self.get(section_id)

    def save_version(self, section_id: str, revision: int, content: str, summary: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO section_versions (
                version_id, section_id, revision, content_markdown, change_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"SV-{uuid.uuid4().hex[:10].upper()}", section_id, revision, content, summary, _now()),
        )
        self.conn.commit()

    def list_versions(self, section_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM section_versions WHERE section_id = ?
            ORDER BY revision
            """,
            (section_id,),
        ).fetchall()
        return [dict(r) for r in rows]


class EvidencePackRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, section_id: str, payload: dict) -> str:
        pack_id = f"EP-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO evidence_packs (evidence_pack_id, section_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (pack_id, section_id, json.dumps(payload, ensure_ascii=False), _now()),
        )
        self.conn.commit()
        return pack_id

    def get(self, pack_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM evidence_packs WHERE evidence_pack_id = ?",
            (pack_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["pack"] = json.loads(d["payload_json"])
        return d

    def get_for_section(self, section_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM evidence_packs WHERE section_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (section_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["pack"] = json.loads(d["payload_json"])
        return d


class ClaimRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def delete_for_section(self, section_id: str) -> None:
        ids = [
            r["claim_id"]
            for r in self.conn.execute(
                "SELECT claim_id FROM claims WHERE section_id = ?", (section_id,)
            ).fetchall()
        ]
        for cid in ids:
            self.conn.execute(
                "DELETE FROM claim_evidence_links WHERE claim_id = ?", (cid,)
            )
        self.conn.execute("DELETE FROM claims WHERE section_id = ?", (section_id,))
        self.conn.commit()

    def save_evidence_item(self, item: dict) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO evidence_items (
                evidence_id, source_id, page, evidence_type, statement,
                block_ids_json, confidence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["evidence_id"],
                item["source_id"],
                item["page"],
                item["evidence_type"],
                item["statement"],
                json.dumps(item.get("block_ids") or []),
                item.get("confidence"),
                json.dumps(item.get("payload") or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def save_claim(self, claim: dict, evidence_ids: list[str]) -> None:
        self.conn.execute(
            """
            INSERT INTO claims (
                claim_id, edition_id, section_id, statement, claim_type,
                importance, verification_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim["claim_id"],
                claim["edition_id"],
                claim["section_id"],
                claim["statement"],
                claim.get("claim_type"),
                claim.get("importance"),
                claim.get("verification_status"),
                json.dumps(claim.get("payload") or {}, ensure_ascii=False),
            ),
        )
        for eid in evidence_ids:
            # metric ids may not be in evidence_items — skip FK failures softly
            exists = self.conn.execute(
                "SELECT 1 FROM evidence_items WHERE evidence_id = ?", (eid,)
            ).fetchone()
            if not exists:
                continue
            self.conn.execute(
                """
                INSERT OR IGNORE INTO claim_evidence_links (claim_id, evidence_id, relation)
                VALUES (?, ?, 'SUPPORTS')
                """,
                (claim["claim_id"], eid),
            )
        self.conn.commit()

    def list_for_section(self, section_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE section_id = ?", (section_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            links = self.conn.execute(
                """
                SELECT e.*
                FROM claim_evidence_links l
                JOIN evidence_items e ON e.evidence_id = l.evidence_id
                WHERE l.claim_id = ?
                """,
                (d["claim_id"],),
            ).fetchall()
            d["evidence"] = [dict(x) for x in links]
            out.append(d)
        return out

    def get_claim(self, claim_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        links = self.conn.execute(
            """
            SELECT e.*
            FROM claim_evidence_links l
            JOIN evidence_items e ON e.evidence_id = l.evidence_id
            WHERE l.claim_id = ?
            """,
            (claim_id,),
        ).fetchall()
        d["evidence"] = [dict(x) for x in links]
        return d


class ChapterRepository:
    """Persistence for chapter-first draft artifacts.

    This repository is optional at runtime: when v2 chapter tables are not present,
    calls become no-ops to preserve compatibility with legacy schema.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def has_v2_tables(self) -> bool:
        for name in ("chapters", "chapter_versions", "paragraphs", "paragraph_evidence_links"):
            row = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (name,),
            ).fetchone()
            if not row:
                return False
        return True

    def save_chapter_draft(
        self,
        *,
        edition_id: str,
        section_id: str,
        order_index: int,
        chapter_key: str,
        draft: ChapterDraft,
        body_markdown: str,
        summary: str | None = None,
    ) -> None:
        if not self.has_v2_tables():
            return

        locked_rows = self.conn.execute(
            """
            SELECT paragraph_id, subsection_key, paragraph_type, text, order_index, edit_state
            FROM paragraphs
            WHERE chapter_id = ? AND edit_state = 'USER_LOCKED'
            ORDER BY order_index
            """,
            (draft.chapter_id,),
        ).fetchall()
        locked_map = {r["paragraph_id"]: dict(r) for r in locked_rows}

        row = self.conn.execute(
            "SELECT chapter_id FROM chapters WHERE chapter_id = ?",
            (draft.chapter_id,),
        ).fetchone()
        now = _now()
        if row:
            self.conn.execute(
                """
                UPDATE chapters
                SET title = ?, chapter_key = ?, order_index = ?, status = ?, updated_at = ?
                WHERE chapter_id = ?
                """,
                (draft.title, chapter_key, order_index, "DRAFT", now, draft.chapter_id),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO chapters (
                    chapter_id, edition_id, chapter_key, title, order_index, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.chapter_id,
                    edition_id,
                    chapter_key,
                    draft.title,
                    order_index,
                    "DRAFT",
                    now,
                    now,
                ),
            )

        rev_row = self.conn.execute(
            "SELECT COALESCE(MAX(revision), 0) AS rev FROM chapter_versions WHERE chapter_id = ?",
            (draft.chapter_id,),
        ).fetchone()
        next_rev = int(rev_row["rev"]) + 1
        self.conn.execute(
            """
            INSERT INTO chapter_versions (
                chapter_version_id, chapter_id, revision, body_markdown, summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"CV-{uuid.uuid4().hex[:10].upper()}",
                draft.chapter_id,
                next_rev,
                body_markdown,
                summary or f"section:{section_id}",
                now,
            ),
        )

        self.conn.execute("DELETE FROM paragraph_evidence_links WHERE paragraph_id IN (SELECT paragraph_id FROM paragraphs WHERE chapter_id = ?)", (draft.chapter_id,))
        self.conn.execute("DELETE FROM paragraphs WHERE chapter_id = ?", (draft.chapter_id,))
        p_order = 0
        seen_locked: set[str] = set()
        for sub in draft.subsections:
            for para in sub.paragraphs:
                locked = locked_map.get(para.paragraph_id)
                text = locked["text"] if locked else para.text
                edit_state = locked["edit_state"] if locked else "AI_EDITABLE"
                if locked:
                    seen_locked.add(para.paragraph_id)
                p_order += 1
                self.conn.execute(
                    """
                    INSERT INTO paragraphs (
                        paragraph_id, chapter_id, subsection_key, paragraph_type, text, order_index, edit_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        para.paragraph_id,
                        draft.chapter_id,
                        sub.subsection_id,
                        para.paragraph_type,
                        text,
                        p_order,
                        edit_state,
                    ),
                )
                for eid in para.evidence_ids:
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO paragraph_evidence_links (paragraph_id, evidence_id)
                        VALUES (?, ?)
                        """,
                        (para.paragraph_id, eid),
                    )
        for pid, locked in locked_map.items():
            if pid in seen_locked:
                continue
            p_order += 1
            self.conn.execute(
                """
                INSERT INTO paragraphs (
                    paragraph_id, chapter_id, subsection_key, paragraph_type, text, order_index, edit_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    draft.chapter_id,
                    locked.get("subsection_key"),
                    locked.get("paragraph_type") or "ANALYSIS",
                    locked.get("text") or "",
                    p_order,
                    "USER_LOCKED",
                ),
            )
        self.conn.commit()

    def get_by_key(self, edition_id: str, chapter_key: str) -> dict | None:
        if not self.has_v2_tables():
            return None
        row = self.conn.execute(
            """
            SELECT * FROM chapters
            WHERE edition_id = ? AND chapter_key = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (edition_id, chapter_key),
        ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, chapter_id: str) -> dict | None:
        if not self.has_v2_tables():
            return None
        row = self.conn.execute(
            "SELECT * FROM chapters WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        return dict(row) if row else None

    def load_draft(self, chapter_id: str) -> ChapterDraft | None:
        if not self.has_v2_tables():
            return None
        chapter = self.get_by_id(chapter_id)
        if not chapter:
            return None
        rows = self.conn.execute(
            """
            SELECT * FROM paragraphs
            WHERE chapter_id = ?
            ORDER BY order_index
            """,
            (chapter_id,),
        ).fetchall()
        from backend.domain.chapter import DraftParagraph, SubsectionDraft

        by_sub: dict[str, list[DraftParagraph]] = {}
        for r in rows:
            eids = [
                x["evidence_id"]
                for x in self.conn.execute(
                    "SELECT evidence_id FROM paragraph_evidence_links WHERE paragraph_id = ?",
                    (r["paragraph_id"],),
                ).fetchall()
            ]
            sub_key = r["subsection_key"] or "SUB-DEFAULT"
            by_sub.setdefault(sub_key, []).append(
                DraftParagraph(
                    paragraph_id=r["paragraph_id"],
                    paragraph_type=r["paragraph_type"] or "FACT",
                    text=r["text"],
                    evidence_ids=eids,
                )
            )
        subsections = [
            SubsectionDraft(subsection_id=k, title=k, paragraphs=v)
            for k, v in by_sub.items()
        ]
        return ChapterDraft(
            chapter_id=chapter_id,
            title=chapter["title"],
            lead="",
            subsections=subsections,
        )

    def update_status(self, chapter_id: str, status: str) -> None:
        if not self.has_v2_tables():
            return
        self.conn.execute(
            "UPDATE chapters SET status = ?, updated_at = ? WHERE chapter_id = ?",
            (status, _now(), chapter_id),
        )
        self.conn.commit()

    def set_paragraph_edit_state(
        self,
        paragraph_id: str,
        edit_state: str,
        *,
        text: str | None = None,
    ) -> dict | None:
        if not self.has_v2_tables():
            return None
        row = self.conn.execute(
            "SELECT * FROM paragraphs WHERE paragraph_id = ?",
            (paragraph_id,),
        ).fetchone()
        if not row:
            return None
        if text is None:
            self.conn.execute(
                "UPDATE paragraphs SET edit_state = ? WHERE paragraph_id = ?",
                (edit_state, paragraph_id),
            )
        else:
            self.conn.execute(
                "UPDATE paragraphs SET edit_state = ?, text = ? WHERE paragraph_id = ?",
                (edit_state, text, paragraph_id),
            )
        self.conn.commit()
        out = self.conn.execute(
            "SELECT * FROM paragraphs WHERE paragraph_id = ?",
            (paragraph_id,),
        ).fetchone()
        return dict(out) if out else None

    def chapter_has_locked_paragraph(self, chapter_id: str) -> bool:
        if not self.has_v2_tables():
            return False
        row = self.conn.execute(
            """
            SELECT 1 FROM paragraphs
            WHERE chapter_id = ? AND edit_state = 'USER_LOCKED'
            LIMIT 1
            """,
            (chapter_id,),
        ).fetchone()
        return bool(row)

    def list_locked_paragraph_texts(self, chapter_id: str) -> list[str]:
        """USER_LOCKED paragraph bodies for Reviser constraint (v2 paragraphs table)."""
        if not self.has_v2_tables():
            return []
        rows = self.conn.execute(
            """
            SELECT text FROM paragraphs
            WHERE chapter_id = ? AND edit_state = 'USER_LOCKED'
            ORDER BY order_index
            """,
            (chapter_id,),
        ).fetchall()
        return [str(r["text"] or "") for r in rows if (r["text"] or "").strip()]
