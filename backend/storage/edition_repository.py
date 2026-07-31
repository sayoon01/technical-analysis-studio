"""Edition / section / claim persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


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
