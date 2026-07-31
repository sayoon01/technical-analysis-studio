"""Planning pipeline: analysis → ReportPlanner → outline wait."""

from __future__ import annotations

import sqlite3

from backend.agents.report_planner.agent import ReportPlannerAgent
from backend.domain.report_plan import CorpusAnalysis
from backend.skills.analysis.corpus_context import _role_text_digest
from backend.domain.enums import SourceRole
from backend.storage.plan_repository import AnalysisRepository, PlanRepository
from backend.storage.repositories import ProjectRepository, SourceRepository


class PlanningPipeline:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
    ) -> None:
        self.conn = conn
        self.agent = ReportPlannerAgent(llm_mode=llm_mode)
        self.analyses = AnalysisRepository(conn)
        self.plans = PlanRepository(conn)
        self.projects = ProjectRepository(conn)
        self.sources = SourceRepository(conn)

    def run(self, project_id: str) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)

        latest = self.analyses.latest(project_id)
        if not latest:
            raise ValueError("No corpus analysis found — run analyze first")

        analysis = CorpusAnalysis.model_validate(latest["analysis"])
        source_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        format_notes = _role_text_digest(
            self.conn, project_id, SourceRole.FORMAT_REFERENCE.value
        )
        previous_notes = _role_text_digest(
            self.conn, project_id, SourceRole.PREVIOUS_EDITION.value
        )
        plan = self.agent.run(
            analysis,
            source_ids=source_ids,
            format_notes=format_notes or None,
            previous_edition_notes=previous_notes or None,
        )
        saved = self.plans.save_plan(project_id, plan)
        self.projects.update_stage(project_id, "WAITING_FOR_OUTLINE_APPROVAL")
        return {
            **saved,
            "outline_count": len(plan.outline),
            "plan": plan.model_dump(),
        }
