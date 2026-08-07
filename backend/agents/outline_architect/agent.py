"""OutlineArchitectAgent — strategy-aligned outline / ReportPlan generation.

Canonical Owner for Outline generation. Does not own workflow, approval,
or persistence (PlanningPipeline / PlanRepository / user Approval).
"""

from __future__ import annotations

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.report_plan import CorpusAnalysis, ReportPlan
from backend.domain.strategy import ReportStrategy
from backend.model_providers.base import (
    LlmError,
    allow_offline_fallback,
    generate_structured,
)
from backend.skills.analysis.offline_planner import plan_offline


class OutlineArchitectAgent:
    """Derive ReportPlan outline hierarchy from Source Intelligence + Strategy."""

    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        analysis: CorpusAnalysis,
        *,
        strategy: ReportStrategy | None = None,
        source_ids: list[str] | None = None,
        format_notes: str | None = None,
        previous_edition_notes: str | None = None,
    ) -> ReportPlan:
        if self.llm_mode == "offline":
            return _apply_strategy(
                plan_offline(analysis, source_ids=source_ids), strategy
            )
        try:
            instruction = load_agent_instruction("outline_architect")
            extras = []
            if format_notes:
                extras.append(
                    "FORMAT_REFERENCE (layout/heading style only — not evidence):\n"
                    + format_notes[:3000]
                )
            if previous_edition_notes:
                extras.append(
                    "PREVIOUS_EDITION upload (tone/structure reference only — not evidence):\n"
                    + previous_edition_notes[:3000]
                )
            extra_block = ("\n\n" + "\n\n".join(extras)) if extras else ""
            user = (
                "Create a ReportPlan JSON for a technical analysis report.\n"
                "Do NOT copy a fixed industry template. Derive outline from this analysis only.\n"
                "Omit chapters that the analysis does not support.\n"
                "expected_visuals may be an empty list.\n"
                "Never cite FORMAT_REFERENCE or PREVIOUS_EDITION uploads as factual sources.\n\n"
                f"{analysis.model_dump_json()}"
                f"{extra_block}"
            )
            if strategy is not None:
                user += (
                    "\n\nUse this ReportStrategy for title and central thesis alignment:\n"
                    f"{strategy.model_dump_json()}"
                )
            plan = generate_structured(
                ReportPlan,
                instruction,
                user,
                agent_name="outline_architect",
                max_retries=1,
            )
            if not plan.outline:
                if not allow_offline_fallback():
                    raise LlmError("OutlineArchitect returned empty outline")
                return _apply_strategy(
                    plan_offline(analysis, source_ids=source_ids), strategy
                )
            normalized = _normalize_plan(plan, source_ids=source_ids)
            return _apply_strategy(normalized, strategy)
        except LlmError:
            if not allow_offline_fallback():
                raise
            return _apply_strategy(plan_offline(analysis, source_ids=source_ids), strategy)
        except Exception:
            if not allow_offline_fallback():
                raise
            return _apply_strategy(plan_offline(analysis, source_ids=source_ids), strategy)


def _normalize_plan(
    plan: ReportPlan, *, source_ids: list[str] | None = None
) -> ReportPlan:
    import uuid

    for i, node in enumerate(plan.outline, start=1):
        if not node.node_id:
            node.node_id = f"N-{uuid.uuid4().hex[:8].upper()}"
        if node.order <= 0:
            node.order = i
        if source_ids and not node.source_scope:
            node.source_scope = list(source_ids)
    return plan


def _apply_strategy(plan: ReportPlan, strategy: ReportStrategy | None) -> ReportPlan:
    if strategy is None:
        return plan
    if strategy.recommended_title:
        plan.title = strategy.recommended_title
    if strategy.subtitle:
        plan.subtitle = strategy.subtitle
    plan.title_candidates = list(strategy.title_candidates or [])
    plan.central_thesis = strategy.central_thesis
    plan.strategy = strategy
    return plan
