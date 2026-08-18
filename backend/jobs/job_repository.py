from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.jobs.job_models import AnalyzeJob


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobAlreadyRunningError(ValueError):
    pass


class JobRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_analyze_job(
        self,
        *,
        project_id: str,
        payload: dict,
        adk_app_name: str,
        adk_user_id: str,
        adk_session_id: str,
    ) -> dict:
        # Friendly error first; DB unique index is final guard.
        row = self.conn.execute(
            """
            SELECT job_id FROM jobs
            WHERE project_id = ? AND job_type = 'ANALYZE'
              AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if row:
            raise JobAlreadyRunningError("Analysis already running for this project")
        job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
        try:
            self.conn.execute(
                """
                INSERT INTO jobs (
                    job_id, project_id, job_type, status, phase, payload_json,
                    adk_app_name, adk_user_id, adk_session_id, created_at
                ) VALUES (?, ?, 'ANALYZE', 'queued', 'analyzing', ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    json.dumps(payload, ensure_ascii=False),
                    adk_app_name,
                    adk_user_id,
                    adk_session_id,
                    _now(),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            if "uq_jobs_active_analyze" in str(exc):
                raise JobAlreadyRunningError(
                    "Analysis already running for this project"
                ) from exc
            raise
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        return dict(row)

    def latest_job_for_project(self, project_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return dict(row) if row else None

    def claim_next_analyze_job(self) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE job_type = 'ANALYZE' AND status = 'queued'
            ORDER BY created_at ASC LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        job_id = row["job_id"]
        self.conn.execute(
            """
            UPDATE jobs
            SET status = 'running', started_at = ?
            WHERE job_id = ? AND status = 'queued'
            """,
            (_now(), job_id),
        )
        self.conn.commit()
        return self.get_job(job_id)

    def mark_running_meta(
        self,
        job_id: str,
        *,
        invocation_id: str | None = None,
        workflow_name: str | None = None,
        agent_name: str | None = None,
        last_event_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE jobs
            SET adk_invocation_id = COALESCE(?, adk_invocation_id),
                current_workflow = COALESCE(?, current_workflow),
                current_agent = COALESCE(?, current_agent),
                last_event_id = COALESCE(?, last_event_id)
            WHERE job_id = ?
            """,
            (invocation_id, workflow_name, agent_name, last_event_id, job_id),
        )
        self.conn.commit()

    def mark_completed(self, job_id: str, *, result: dict | None = None) -> None:
        self.conn.execute(
            """
            UPDATE jobs
            SET status = 'completed', finished_at = ?, result_json = ?
            WHERE job_id = ?
            """,
            (_now(), json.dumps(result, ensure_ascii=False) if result else None, job_id),
        )
        self.conn.commit()

    def mark_failed(self, job_id: str, *, error_message: str) -> None:
        self.conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', finished_at = ?, error_message = ?
            WHERE job_id = ?
            """,
            (_now(), error_message[:500], job_id),
        )
        self.conn.commit()

    def add_job_event(
        self,
        *,
        job_id: str,
        sequence_no: int,
        event_type: str,
        workflow_name: str | None,
        agent_name: str | None,
        invocation_id: str | None,
        session_id: str | None,
        progress: float | None,
        sanitized_error_code: str | None,
    ) -> None:
        event_id = f"JEV-{uuid.uuid4().hex[:12].upper()}"
        self.conn.execute(
            """
            INSERT INTO job_events (
                job_event_id, job_id, sequence_no, event_type, workflow_name,
                agent_name, invocation_id, session_id, progress, sanitized_error_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                job_id,
                sequence_no,
                event_type,
                workflow_name,
                agent_name,
                invocation_id,
                session_id,
                progress,
                sanitized_error_code,
                _now(),
            ),
        )
        self.conn.commit()
