"""ReportPlannerAgent — dynamic title/outline from CorpusAnalysis."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.report_plan import CorpusAnalysis, ReportPlan
from backend.model_providers.base import (
    LlmError,
    allow_offline_fallback,
    generate_structured,
)
from backend.skills.analysis.offline_planner import plan_offline


class ReportPlannerAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        analysis: CorpusAnalysis,
        *,
        source_ids: list[str] | None = None,
        format_notes: str | None = None,
        previous_edition_notes: str | None = None,
    ) -> ReportPlan:
        if self.llm_mode == "offline":
            return plan_offline(analysis, source_ids=source_ids)
        try:
            instruction = load_agent_instruction("report_planner")
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
            plan = generate_structured(
                ReportPlan,
                instruction,
                user,
                agent_name="report_planner",
                max_retries=1,
            )
            if not plan.outline:
                if not allow_offline_fallback():
                    raise LlmError("Planner returned empty outline")
                return plan_offline(analysis, source_ids=source_ids)
            # Ensure node_ids / orders exist
            return _normalize_plan(plan, source_ids=source_ids)
        except LlmError:
            if not allow_offline_fallback():
                raise
            return plan_offline(analysis, source_ids=source_ids)
        except Exception:
            if not allow_offline_fallback():
                raise
            return plan_offline(analysis, source_ids=source_ids)


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
