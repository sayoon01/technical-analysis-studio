"""Analyze job use-case (Phase 1 ADK vertical slice)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from backend.domain.enums import ProjectStage
from backend.jobs.job_repository import JobAlreadyRunningError, JobRepository
from backend.services.job_status import lock_for
from backend.storage.repositories import ProjectRepository, SourceRepository


class AnalyzeJobUseCase:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.projects = ProjectRepository(conn)
        self.sources = SourceRepository(conn)
        self.jobs = JobRepository(conn)

    def start(self, project_id: str) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        if lock_for(project_id).locked():
            raise ValueError("Analysis already running for this project")
        ready_sources = [
            s
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        if not ready_sources:
            raise ValueError("No READY evidence sources to analyze")
        payload = {
            "project_id": project_id,
            "source_ids": [s["source_id"] for s in ready_sources],
        }
        adk_session_id = f"SES-{uuid.uuid4().hex[:16]}"
        try:
            job = self.jobs.create_analyze_job(
                project_id=project_id,
                payload=payload,
                adk_app_name="technical_analysis",
                adk_user_id=project_id,
                adk_session_id=adk_session_id,
            )
        except JobAlreadyRunningError:
            raise ValueError("Analysis already running for this project") from None
        self.projects.update_stage(project_id, ProjectStage.ANALYZING.value)
        latest = self._latest_analysis(project_id)
        return {
            "accepted": True,
            "project_id": project_id,
            "job_id": job["job_id"],
            "phase": "analyzing",
            "busy": True,
            "analysis_id": latest.get("analysis_id") if latest else None,
            "analysis": latest.get("analysis") if latest else None,
        }

    def _latest_analysis(self, project_id: str) -> dict | None:
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
        try:
            d["analysis"] = json.loads(d.get("payload_json") or "{}")
        except json.JSONDecodeError:
            d["analysis"] = {}
        return d
