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

    def save_validator(self, section_id: str, draft_validation) -> str:
        """Persist DraftValidator issues (reviewer_type=validator). Not an LLM review."""
        from backend.domain.enums import ReviewDecision

        decision = (
            ReviewDecision.PASS.value
            if getattr(draft_validation, "ok", True)
            else ReviewDecision.REVISE.value
        )
        payload = (
            draft_validation.model_dump(mode="json")
            if hasattr(draft_validation, "model_dump")
            else dict(draft_validation)
        )
        issues = list(getattr(draft_validation, "issues", []) or [])
        return self._save(section_id, "validator", decision, payload, issues)

    def save_editorial_full_report(self, edition_id: str, review: EditorialReview) -> str:
        synthetic_section_id = f"FULL-{edition_id}"
        return self._save(
            synthetic_section_id,
            "editorial_full_report",
            review.decision.value,
            review.model_dump(mode="json"),
            review.issues,
        )

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
        out = []
        for r in rows:
            d = dict(r)
            # Frontend compatibility: message || detail || description
            if not d.get("message"):
                d["message"] = d.get("description") or ""
            if not d.get("detail"):
                d["detail"] = d.get("description") or ""
            out.append(d)
        return out

    def list_full_report_reviews(self, edition_id: str) -> list[dict]:
        synthetic_section_id = f"FULL-{edition_id}"
        rows = self.conn.execute(
            """
            SELECT * FROM reviews
            WHERE section_id = ? AND reviewer_type = 'editorial_full_report'
            ORDER BY created_at DESC
            """,
            (synthetic_section_id,),
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

    def mark_issues_resolved(self, issue_ids: list[str]) -> None:
        for iid in issue_ids:
            self.conn.execute(
                "UPDATE review_issues SET status = 'RESOLVED' WHERE issue_id = ?",
                (iid,),
            )
        self.conn.commit()
