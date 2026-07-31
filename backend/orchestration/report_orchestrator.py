"""ReportOrchestrator — stage-driven; LLM does not choose global workflow."""

from __future__ import annotations

from typing import Any

from backend.domain.enums import ProjectStage


class ReportOrchestrator:
    """Thin stage facade over existing pipelines/services (no parallel workflow)."""

    def __init__(
        self,
        project_service: Any,
        *,
        analysis_pipeline: Any | None = None,
        planning_pipeline: Any | None = None,
        production_pipeline: Any | None = None,
        review_loop: Any | None = None,
        finalization_pipeline: Any | None = None,
        edition_service: Any | None = None,
    ) -> None:
        self.project_service = project_service
        self.analysis_pipeline = analysis_pipeline
        self.planning_pipeline = planning_pipeline
        self.production_pipeline = production_pipeline
        self.review_loop = review_loop
        self.finalization_pipeline = finalization_pipeline
        self.edition_service = edition_service

    def run_sync(self, project_id: str) -> str | None:
        """Advance one stage. Returns new stage or None if waiting/idle."""
        project = self.project_service.get(project_id)
        stage = ProjectStage(
            project["stage"] if isinstance(project, dict) else project.stage
        )

        if stage == ProjectStage.ANALYZING and self.analysis_pipeline:
            self.analysis_pipeline.run(project_id)
            return ProjectStage.PLANNING.value
        if stage == ProjectStage.PLANNING and self.planning_pipeline:
            self.planning_pipeline.run(project_id)
            return ProjectStage.WAITING_FOR_OUTLINE_APPROVAL.value
        if stage == ProjectStage.WAITING_FOR_OUTLINE_APPROVAL:
            return None
        if stage == ProjectStage.PRODUCING:
            if self.edition_service:
                result = self.edition_service.produce(project_id, auto_review=True)
                return result.get("stage")
            if self.production_pipeline:
                result = self.production_pipeline.run(project_id)
                edition_id = result.get("edition_id")
                if self.review_loop and edition_id:
                    reviewed = self.review_loop.run_edition(edition_id)
                    return reviewed.get("stage")
                return ProjectStage.REVIEWING.value
        if stage == ProjectStage.REVIEWING and self.review_loop:
            project = self.project_service.get(project_id)
            edition_id = (
                project.get("current_edition_id")
                if isinstance(project, dict)
                else None
            )
            if not edition_id:
                return None
            reviewed = self.review_loop.run_edition(edition_id)
            return reviewed.get("stage")
        if stage == ProjectStage.FINALIZING and self.finalization_pipeline:
            self.finalization_pipeline.run(project_id)
            return ProjectStage.READY_FOR_EXPORT.value
        return None

    async def run(self, project_id: str) -> None:
        self.run_sync(project_id)
