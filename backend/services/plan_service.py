"""Plan / outline / analysis application service."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from backend.domain.enums import ProjectStage
from backend.domain.report_plan import OutlineNode
from backend.orchestration.analysis_pipeline import AnalysisPipeline
from backend.orchestration.planning_pipeline import PlanningPipeline
from backend.orchestration.state_machine import assert_transition
from backend.storage.plan_repository import AnalysisRepository, PlanRepository
from backend.storage.repositories import ProjectRepository

_analyze_locks: dict[str, threading.Lock] = {}
_analyze_locks_guard = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_guard = threading.Lock()

_PHASE_LABELS = {
    "analyzing": "자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다",
    "planning": "목차 생성 중 (Ollama) — 수 분 걸릴 수 있습니다",
}


def _lock_for(project_id: str) -> threading.Lock:
    with _analyze_locks_guard:
        if project_id not in _analyze_locks:
            _analyze_locks[project_id] = threading.Lock()
        return _analyze_locks[project_id]


def _set_job(project_id: str, phase: str | None) -> None:
    with _jobs_guard:
        if phase is None:
            _jobs.pop(project_id, None)
            return
        prev = _jobs.get(project_id) or {}
        _jobs[project_id] = {
            "phase": phase,
            "label": _PHASE_LABELS.get(phase, phase),
            "started_at": prev.get("started_at")
            or datetime.now(timezone.utc).isoformat(),
        }


def _get_job(project_id: str) -> dict | None:
    with _jobs_guard:
        job = _jobs.get(project_id)
        return dict(job) if job else None


class PlanService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
    ) -> None:
        self.conn = conn
        self.llm_mode = llm_mode
        self.projects = ProjectRepository(conn)
        self.analyses = AnalysisRepository(conn)
        self.plans = PlanRepository(conn)
        self.analysis_pipeline = AnalysisPipeline(conn, llm_mode=llm_mode)
        self.planning_pipeline = PlanningPipeline(conn, llm_mode=llm_mode)

    def generation_status(self, project_id: str) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        job = _get_job(project_id)
        lock = _lock_for(project_id)
        busy = lock.locked() or bool(job)
        phase = (job or {}).get("phase")
        if not phase and busy:
            stage = project["stage"]
            if stage == ProjectStage.ANALYZING.value:
                phase = "analyzing"
            elif stage == ProjectStage.PLANNING.value:
                phase = "planning"
        return {
            "project_id": project_id,
            "stage": project["stage"],
            "busy": busy,
            "phase": phase,
            "label": (job or {}).get("label")
            or (_PHASE_LABELS.get(phase or "") if phase else None),
            "started_at": (job or {}).get("started_at"),
            "current_edition_id": project.get("current_edition_id"),
        }

    def analyze(self, project_id: str) -> dict:
        if not self.projects.get(project_id):
            raise KeyError(project_id)
        lock = _lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("Analysis already running for this project")
        _set_job(project_id, "analyzing")
        try:
            # Allow analyze from ANALYZING or after ingest
            project = self.projects.get(project_id)
            stage = ProjectStage(project["stage"])
            if stage in {ProjectStage.CREATED, ProjectStage.INGESTING}:
                raise ValueError(f"Sources not ready (stage={stage})")
            if stage not in {
                ProjectStage.ANALYZING,
                ProjectStage.PLANNING,
                ProjectStage.WAITING_FOR_OUTLINE_APPROVAL,
                ProjectStage.FAILED,
            }:
                # Re-analyze from later stages is allowed by resetting to ANALYZING
                self.projects.update_stage(project_id, ProjectStage.ANALYZING.value)
            elif stage != ProjectStage.ANALYZING:
                self.projects.update_stage(project_id, ProjectStage.ANALYZING.value)
            return self.analysis_pipeline.run(project_id)
        finally:
            _set_job(project_id, None)
            lock.release()

    def generate_plan(self, project_id: str) -> dict:
        if not self.projects.get(project_id):
            raise KeyError(project_id)
        lock = _lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("Outline generation already running for this project")
        _set_job(project_id, "planning")
        try:
            project = self.projects.get(project_id)
            if project["stage"] not in {
                ProjectStage.PLANNING.value,
                ProjectStage.WAITING_FOR_OUTLINE_APPROVAL.value,
                ProjectStage.ANALYZING.value,
            }:
                # ensure analysis exists
                if not self.analyses.latest(project_id):
                    _set_job(project_id, "analyzing")
                    self.analysis_pipeline.run(project_id)
                    _set_job(project_id, "planning")
                else:
                    self.projects.update_stage(project_id, ProjectStage.PLANNING.value)
            elif project["stage"] == ProjectStage.ANALYZING.value:
                if not self.analyses.latest(project_id):
                    _set_job(project_id, "analyzing")
                    self.analysis_pipeline.run(project_id)
                    _set_job(project_id, "planning")
                else:
                    self.projects.update_stage(project_id, ProjectStage.PLANNING.value)
            return self.planning_pipeline.run(project_id)
        finally:
            _set_job(project_id, None)
            lock.release()

    def get_analysis(self, project_id: str) -> dict:
        row = self.analyses.latest(project_id)
        if not row:
            raise KeyError(project_id)
        return row

    def get_plan(self, project_id: str) -> dict:
        row = self.plans.latest_plan(project_id)
        if not row:
            raise KeyError(project_id)
        return row

    def get_outline(self, project_id: str) -> dict:
        row = self.plans.get_outline(project_id)
        if not row:
            raise KeyError(project_id)
        return row

    def patch_plan(self, project_id: str, **fields) -> dict:
        plan = self.plans.latest_plan(project_id)
        if not plan:
            raise KeyError(project_id)
        self.plans.update_plan_fields(plan["plan_id"], **fields)
        return self.plans.latest_plan(project_id)

    def patch_outline(self, project_id: str, nodes: list[dict]) -> dict:
        outline = self.plans.get_outline(project_id)
        if not outline:
            raise KeyError(project_id)
        validated = [OutlineNode.model_validate(n) for n in nodes]
        self.plans.replace_nodes(outline["outline_id"], validated)
        return self.plans.get_outline(project_id)

    def recommend_node(self, project_id: str, node_id: str) -> dict:
        """Re-derive a single node objective from current analysis (offline-safe)."""
        analysis_row = self.analyses.latest(project_id)
        outline = self.plans.get_outline(project_id)
        if not analysis_row or not outline:
            raise KeyError(project_id)
        nodes = outline["nodes"]
        target = next((n for n in nodes if n["node_id"] == node_id), None)
        if not target:
            raise KeyError(node_id)
        analysis = analysis_row["analysis"]
        topic = analysis.get("main_topic", "")
        target["objective"] = (
            f"{target['title']}에 대해 {topic} 자료에서 확인되는 근거만으로 서술한다."
        )
        if not target.get("analysis_questions"):
            target["analysis_questions"] = [
                f"{target['title']}과 관련된 핵심 근거는 무엇인가?"
            ]
        self.plans.replace_nodes(outline["outline_id"], nodes)
        return target

    def approve_outline(self, project_id: str) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        outline = self.plans.get_outline(project_id)
        if not outline:
            raise KeyError(project_id)
        current = ProjectStage(project["stage"])
        assert_transition(current, ProjectStage.PRODUCING)
        self.plans.approve(outline["outline_id"])
        self.projects.update_stage(project_id, ProjectStage.PRODUCING.value)
        return {
            "project_id": project_id,
            "outline_id": outline["outline_id"],
            "stage": ProjectStage.PRODUCING.value,
            "approved": True,
        }

    def get_metrics(self, project_id: str) -> list[dict]:
        sources = self.conn.execute(
            "SELECT source_id FROM sources WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        ids = [r["source_id"] for r in sources]
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM metric_facts WHERE source_id IN ({ph})",
            ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_evidence_gaps(self, project_id: str) -> list[str]:
        row = self.analyses.latest(project_id)
        if not row:
            return []
        return list(row["analysis"].get("evidence_gaps") or [])
