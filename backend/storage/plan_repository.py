"""Plan / outline / analysis persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.domain.report_plan import CorpusAnalysis, OutlineNode, ReportPlan


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(
        self, project_id: str, analysis: CorpusAnalysis, snapshot_id: str | None = None
    ) -> dict:
        analysis_id = f"AN-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO corpus_analyses (analysis_id, project_id, snapshot_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                project_id,
                snapshot_id,
                analysis.model_dump_json(),
                _now(),
            ),
        )
        self.conn.commit()
        return {"analysis_id": analysis_id, "project_id": project_id}

    def latest(self, project_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM corpus_analyses
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["analysis"] = json.loads(d["payload_json"])
        return d


class PlanRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_plan(
        self,
        project_id: str,
        plan: ReportPlan,
        *,
        snapshot_id: str | None = None,
    ) -> dict:
        plan_id = f"PLN-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO report_plans (
                plan_id, project_id, snapshot_id, title, subtitle, purpose,
                target_reader, report_summary, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                project_id,
                snapshot_id,
                plan.title,
                plan.subtitle,
                plan.purpose,
                plan.target_reader,
                plan.report_summary,
                plan.model_dump_json(),
                _now(),
            ),
        )
        outline_id = f"OUT-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO outlines (outline_id, plan_id, version, approved)
            VALUES (?, ?, 1, 0)
            """,
            (outline_id, plan_id),
        )
        self._insert_nodes(outline_id, plan.outline)
        self.conn.commit()
        return {
            "plan_id": plan_id,
            "outline_id": outline_id,
            "project_id": project_id,
            "title": plan.title,
        }

    def latest_plan(self, project_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM report_plans
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["plan"] = json.loads(d["payload_json"])
        outline = self.conn.execute(
            """
            SELECT * FROM outlines WHERE plan_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (d["plan_id"],),
        ).fetchone()
        if outline:
            d["outline_id"] = outline["outline_id"]
            d["approved"] = bool(outline["approved"])
            d["outline_nodes"] = self.list_nodes(outline["outline_id"])
        return d

    def list_nodes(self, outline_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM outline_nodes
            WHERE outline_id = ?
            ORDER BY "order"
            """,
            (outline_id,),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            payload = json.loads(item.pop("payload_json") or "{}")
            item.update(payload)
            out.append(item)
        return out

    def get_outline(self, project_id: str) -> dict | None:
        plan = self.latest_plan(project_id)
        if not plan:
            return None
        return {
            "outline_id": plan.get("outline_id"),
            "plan_id": plan["plan_id"],
            "approved": plan.get("approved", False),
            "title": plan["title"],
            "subtitle": plan.get("subtitle"),
            "nodes": plan.get("outline_nodes") or [],
        }

    def replace_nodes(self, outline_id: str, nodes: list[OutlineNode] | list[dict]) -> None:
        self.conn.execute(
            "DELETE FROM outline_nodes WHERE outline_id = ?", (outline_id,)
        )
        parsed: list[OutlineNode] = []
        for n in nodes:
            if isinstance(n, OutlineNode):
                parsed.append(n)
            else:
                parsed.append(OutlineNode.model_validate(n))
        self._insert_nodes(outline_id, parsed)
        # bump version
        self.conn.execute(
            "UPDATE outlines SET version = version + 1 WHERE outline_id = ?",
            (outline_id,),
        )
        self.conn.commit()

    def update_plan_fields(self, plan_id: str, **fields: Any) -> None:
        allowed = {"title", "subtitle", "purpose", "target_reader", "report_summary"}
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k in allowed and v is not None:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            vals.append(plan_id)
            self.conn.execute(
                f"UPDATE report_plans SET {', '.join(sets)} WHERE plan_id = ?",
                vals,
            )
            # sync payload title fields
            row = self.conn.execute(
                "SELECT payload_json FROM report_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if row:
                payload = json.loads(row["payload_json"])
                for k, v in fields.items():
                    if k in allowed and v is not None:
                        payload[k] = v
                self.conn.execute(
                    "UPDATE report_plans SET payload_json = ? WHERE plan_id = ?",
                    (json.dumps(payload, ensure_ascii=False), plan_id),
                )
            self.conn.commit()

    def approve(self, outline_id: str) -> None:
        self.conn.execute(
            """
            UPDATE outlines SET approved = 1, approved_at = ? WHERE outline_id = ?
            """,
            (_now(), outline_id),
        )
        self.conn.commit()

    def _insert_nodes(self, outline_id: str, nodes: list[OutlineNode]) -> None:
        for n in nodes:
            payload = n.model_dump()
            self.conn.execute(
                """
                INSERT INTO outline_nodes (
                    node_id, outline_id, parent_id, level, "order",
                    title, objective, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    n.node_id,
                    outline_id,
                    n.parent_id,
                    n.level,
                    n.order,
                    n.title,
                    n.objective,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
