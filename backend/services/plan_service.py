"""Plan / outline / analysis application service."""

from __future__ import annotations

import sqlite3

from backend.domain.enums import ProjectStage
from backend.domain.report_plan import OutlineNode
from backend.orchestration.analysis_pipeline import AnalysisPipeline
from backend.orchestration.planning_pipeline import PlanningPipeline
from backend.orchestration.state_machine import assert_transition
from backend.services.job_status import (
    PHASE_LABELS,
    get_job,
    lock_for,
    set_job,
)
from backend.jobs.job_repository import JobRepository
from backend.storage.plan_repository import AnalysisRepository, PlanRepository
from backend.storage.repositories import ProjectRepository
from backend.application.analyze_jobs import AnalyzeJobUseCase


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
        job_repo = JobRepository(self.conn)
        persistent = job_repo.latest_job_for_project(project_id)
        if persistent and persistent.get("job_type") == "ANALYZE":
            status_text = persistent.get("status")
            stage = str(project["stage"])
            busy = status_text in {"queued", "running"} and stage in {
                ProjectStage.ANALYZING.value,
                ProjectStage.PLANNING.value,
                ProjectStage.WAITING_FOR_OUTLINE_APPROVAL.value,
            }
            phase = persistent.get("phase") if busy else None
            interrupted = False
            if not busy and project["stage"] == ProjectStage.PRODUCING.value:
                eid = project.get("current_edition_id")
                if eid:
                    row = self.conn.execute(
                        "SELECT status FROM report_editions WHERE edition_id = ?",
                        (eid,),
                    ).fetchone()
                    if row and row["status"] == "PRODUCING":
                        interrupted = True
            status: dict = {
                "project_id": project_id,
                "stage": project["stage"],
                "busy": busy,
                "phase": phase,
                "label": PHASE_LABELS.get(phase or "", phase),
                "started_at": persistent.get("started_at"),
                "current_edition_id": project.get("current_edition_id"),
                "interrupted": interrupted,
            }
            if status_text == "failed" and persistent.get("error_message"):
                status["error"] = persistent["error_message"]
            return status
        job = get_job(project_id)
        lock = lock_for(project_id)
        # Only live in-process jobs count as busy. DB stage/edition status can
        # remain PRODUCING after server restart; treating that as busy falsely
        # locks the UI and pretends writing is still running.
        busy = lock.locked() or bool(job)
        phase = (job or {}).get("phase")
        if not phase and busy:
            stage = project["stage"]
            if stage == ProjectStage.ANALYZING.value:
                phase = "analyzing"
            elif stage == ProjectStage.PLANNING.value:
                phase = "planning"
            elif stage == ProjectStage.PRODUCING.value:
                phase = "producing"
            elif stage == ProjectStage.REVIEWING.value:
                phase = "reviewing"
        interrupted = False
        if not busy and project["stage"] == ProjectStage.PRODUCING.value:
            eid = project.get("current_edition_id")
            if eid:
                row = self.conn.execute(
                    "SELECT status FROM report_editions WHERE edition_id = ?",
                    (eid,),
                ).fetchone()
                if row and row["status"] == "PRODUCING":
                    interrupted = True
        from backend.services.job_status import get_job_outcome

        outcome = get_job_outcome(project_id) if not busy else None
        status: dict = {
            "project_id": project_id,
            "stage": project["stage"],
            "busy": busy,
            "phase": phase,
            "label": (job or {}).get("label")
            or (PHASE_LABELS.get(phase or "") if phase else None),
            "started_at": (job or {}).get("started_at"),
            "current_edition_id": project.get("current_edition_id"),
            "interrupted": interrupted,
        }
        # Additive progress / failure projection (unknown fields ignored by older FE).
        if job:
            for key in (
                "current_section",
                "current_section_title",
                "current_step",
                "completed_sections",
                "total_sections",
            ):
                if key in job:
                    status[key] = job[key]
        if outcome:
            if outcome.get("error"):
                status["error"] = outcome["error"]
            if outcome.get("failed_step"):
                status["failed_step"] = outcome["failed_step"]
            if outcome.get("failed_section"):
                status["failed_section"] = outcome["failed_section"]
            if outcome.get("result") is not None:
                status["review_result"] = outcome["result"]
            if outcome.get("finished_at"):
                status["finished_at"] = outcome["finished_at"]
        return status

    def analyze(self, project_id: str) -> dict:
        return AnalyzeJobUseCase(self.conn).start(project_id)

    def generate_plan(self, project_id: str) -> dict:
        if not self.projects.get(project_id):
            raise KeyError(project_id)
        lock = lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("Outline generation already running for this project")
        set_job(project_id, "planning")
        try:
            project = self.projects.get(project_id)
            if project["stage"] not in {
                ProjectStage.PLANNING.value,
                ProjectStage.WAITING_FOR_OUTLINE_APPROVAL.value,
                ProjectStage.ANALYZING.value,
            }:
                # ensure analysis exists
                if not self.analyses.latest(project_id):
                    set_job(project_id, "analyzing")
                    self.analysis_pipeline.run(project_id)
                    set_job(project_id, "planning")
                else:
                    self.projects.update_stage(project_id, ProjectStage.PLANNING.value)
            elif project["stage"] == ProjectStage.ANALYZING.value:
                if not self.analyses.latest(project_id):
                    set_job(project_id, "analyzing")
                    self.analysis_pipeline.run(project_id)
                    set_job(project_id, "planning")
                else:
                    self.projects.update_stage(project_id, ProjectStage.PLANNING.value)
            return self.planning_pipeline.run(project_id)
        finally:
            set_job(project_id, None)
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
        topic = analysis.get("main_topic", "") or "본"
        target["objective"] = (
            f"{target['title']}에 대해 {topic} 자료를 바탕으로, "
            "근거 있는 사실과 그에 대한 전문 분석을 서술한다. "
            "수치·구체 사실은 출처를 밝히고, 자료에서 확인되지 않은 내용은 한계·미확인으로 명시한다."
        )
        if not target.get("analysis_questions"):
            target["analysis_questions"] = [
                f"{target['title']}에서 확인할 핵심 사실과 분석 포인트는 무엇인가?",
                f"{target['title']} 관련 자료 공백·한계는 무엇인가?",
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
