"""Persist reviews and issues."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.domain.review import EditorialReview, TechnicalReview


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_technical(self, section_id: str, review: TechnicalReview) -> str:
        return self._save(section_id, "technical", review.decision.value, review.model_dump(mode="json"), review.issues)

    def save_editorial(self, section_id: str, review: EditorialReview) -> str:
        return self._save(section_id, "editorial", review.decision.value, review.model_dump(mode="json"), review.issues)

    def _save(self, section_id: str, reviewer_type: str, decision: str, payload: dict, issues) -> str:
        review_id = f"RV-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO reviews (review_id, section_id, reviewer_type, decision, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                section_id,
                reviewer_type,
                decision,
                json.dumps(payload, ensure_ascii=False),
                _now(),
            ),
        )
        for iss in issues:
            self.conn.execute(
                """
                INSERT INTO review_issues (
                    issue_id, review_id, section_id, reviewer_type, severity,
                    issue_type, paragraph_id, description, recommendation, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iss.issue_id,
                    review_id,
                    section_id,
                    iss.reviewer_type,
                    iss.severity.value if hasattr(iss.severity, "value") else iss.severity,
                    iss.issue_type,
                    iss.paragraph_id,
                    iss.description,
                    iss.recommendation,
                    iss.status,
                ),
            )
        self.conn.commit()
        return review_id

    def list_for_section(self, section_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM reviews WHERE section_id = ?
            ORDER BY created_at DESC
            """,
            (section_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload_json"])
            d["issues"] = [
                dict(i)
                for i in self.conn.execute(
                    "SELECT * FROM review_issues WHERE review_id = ?",
                    (d["review_id"],),
                ).fetchall()
            ]
            out.append(d)
        return out

    def open_issues(self, section_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM review_issues
            WHERE section_id = ? AND status = 'OPEN'
            ORDER BY severity
            """,
            (section_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_issues_resolved(self, issue_ids: list[str]) -> None:
        for iid in issue_ids:
            self.conn.execute(
                "UPDATE review_issues SET status = 'RESOLVED' WHERE issue_id = ?",
                (iid,),
            )
        self.conn.commit()
