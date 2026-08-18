from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.adk_app.event_projection import (
    event_progress,
    projectable_event_type,
    sanitized_error_code,
)
from backend.adk_app.runner_runtime import run_analyze_job_sync
from backend.config import settings
from backend.domain.report_plan import CorpusAnalysis
from backend.jobs.job_repository import JobRepository
from backend.storage.database import connect
from backend.storage.plan_repository import AnalysisRepository
from backend.storage.repositories import ProjectRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_error(exc: Exception) -> tuple[str, str]:
    msg = str(exc)
    if "timeout" in msg.lower():
        return ("MODEL_TIMEOUT", "Model request timeout")
    return ("WORKFLOW_FAILED", msg[:300])


class AnalyzeJobWorker:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.jobs = JobRepository(conn)
        self.analyses = AnalysisRepository(conn)
        self.projects = ProjectRepository(conn)

    def run_once(self) -> bool:
        job = self.jobs.claim_next_analyze_job()
        if not job:
            return False
        self._run_job(job)
        return True

    def run_forever(self, poll_seconds: float = 1.0) -> None:
        while True:
            ran = self.run_once()
            if not ran:
                time.sleep(poll_seconds)

    def _run_job(self, job: dict) -> None:
        payload = json.loads(job["payload_json"] or "{}")
        project_id = job["project_id"]
        app_name = job["adk_app_name"]
        user_id = job["adk_user_id"]
        session_id = job["adk_session_id"]
        invocation_id = f"INV-{uuid.uuid4().hex[:16]}"
        self.jobs.mark_running_meta(
            job["job_id"],
            invocation_id=invocation_id,
            workflow_name="analysis",
            agent_name="TechnicalAnalysisRootAgent",
        )
        seq = 0

        def on_event(event):
            nonlocal seq
            seq += 1
            self.jobs.add_job_event(
                job_id=job["job_id"],
                sequence_no=seq,
                event_type=projectable_event_type(event),
                workflow_name="analysis",
                agent_name=getattr(event, "author", None),
                invocation_id=getattr(event, "invocation_id", None)
                or getattr(event, "invocationId", None),
                session_id=session_id,
                progress=event_progress(event),
                sanitized_error_code=sanitized_error_code(event),
            )
            self.jobs.mark_running_meta(
                job["job_id"],
                agent_name=getattr(event, "author", None) or "unknown",
                last_event_id=getattr(event, "id", None),
            )

        initial_state = self._build_initial_state(payload)
        try:
            result = run_analyze_job_sync(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                invocation_id=invocation_id,
                initial_state=initial_state,
                on_event=on_event,
            )
            self._persist_outputs(project_id, result)
            self.jobs.mark_completed(job["job_id"], result={"saved": True})
        except Exception as exc:
            code, msg = _sanitize_error(exc)
            self.jobs.mark_failed(job["job_id"], error_message=msg)
            self.jobs.add_job_event(
                job_id=job["job_id"],
                sequence_no=seq + 1,
                event_type="error",
                workflow_name="analysis",
                agent_name="AnalyzeJobWorker",
                invocation_id=invocation_id,
                session_id=session_id,
                progress=None,
                sanitized_error_code=code,
            )

    def _build_initial_state(self, payload: dict) -> dict:
        project_id = payload["project_id"]
        source_ids = payload.get("source_ids") or []
        rows = self.conn.execute(
            """
            SELECT block_id, source_id, page_number, text
            FROM content_blocks
            WHERE source_id IN ({})
            ORDER BY source_id, page_number, reading_order
            LIMIT 80
            """.format(",".join("?" for _ in source_ids)),
            source_ids,
        ).fetchall()
        candidates = [
            {
                "evidence_id": f"EVD-{r['block_id']}",
                "source_id": r["source_id"],
                "page_number": r["page_number"],
                "text": (r["text"] or "")[:300],
            }
            for r in rows
        ]
        source_batch = {
            "project_id": project_id,
            "source_ids": source_ids,
            "blocks": candidates,
        }
        return {
            "workflow_name": "analysis",
            "source_batch": source_batch,
            "analysis_constraints": {
                "grounding_required": True,
                "no_fabrication": True,
            },
            "evidence_candidates": candidates,
            "evidence_rules": {
                "accepted": "supported by explicit source text",
                "rejected": "insufficient support",
                "failed": "broken or unreadable candidate",
            },
        }

    def _persist_outputs(self, project_id: str, result: dict) -> None:
        validated = result.get("source_intelligence_validated")
        if not isinstance(validated, dict):
            raise ValueError("Missing source_intelligence_validated")
        analysis = CorpusAnalysis.model_validate(
            {
                **validated,
                "quantitative_findings": [],
                "previous_edition_analysis": None,
            }
        )
        self.analyses.save(project_id, analysis)
        self._save_artifact(project_id, "SOURCE_INTELLIGENCE_RAW", result.get("source_intelligence_raw"))
        self._save_artifact(project_id, "SOURCE_INTELLIGENCE_VALIDATED", validated)
        self._save_artifact(project_id, "EVIDENCE_DECISION_RAW", result.get("evidence_decision_raw"))
        self._save_artifact(
            project_id,
            "EVIDENCE_DECISION_VALIDATED",
            result.get("evidence_decision_validated"),
        )

    def _save_artifact(self, project_id: str, artifact_type: str, payload) -> None:
        artifact_id = f"ART-{uuid.uuid4().hex[:12].upper()}"
        root = settings.data_dir.resolve() / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        path = (root / f"{artifact_id}.json").resolve()
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.conn.execute(
            """
            INSERT INTO artifacts (artifact_id, project_id, edition_id, artifact_type, storage_path, created_at)
            VALUES (?, ?, NULL, ?, ?, ?)
            """,
            (artifact_id, project_id, artifact_type, str(path), _now()),
        )
        self.conn.commit()


def run_worker_forever() -> None:
    conn = connect()
    AnalyzeJobWorker(conn).run_forever()
