"""OutlineDesignerAgent — strategy-aligned outline generation."""

from __future__ import annotations

from backend.agents.report_planner.agent import ReportPlannerAgent
from backend.domain.report_plan import CorpusAnalysis, ReportPlan
from backend.domain.strategy import ReportStrategy


class OutlineDesignerAgent:
    """Thin wrapper to keep phase migration explicit.

    For now it reuses ReportPlannerAgent generation behavior and naming will
    be decoupled in later commits.
    """

    def __init__(self, *, llm_mode: str | None = None) -> None:
        self._planner = ReportPlannerAgent(llm_mode=llm_mode)

    def run(
        self,
        analysis: CorpusAnalysis,
        *,
        strategy: ReportStrategy,
        source_ids: list[str] | None = None,
        format_notes: str | None = None,
        previous_edition_notes: str | None = None,
    ) -> ReportPlan:
        return self._planner.run(
            analysis,
            strategy=strategy,
            source_ids=source_ids,
            format_notes=format_notes,
            previous_edition_notes=previous_edition_notes,
        )
