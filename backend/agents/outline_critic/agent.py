"""OutlineCriticAgent — critique generated outline quality."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.enums import IssueSeverity, ReviewDecision
from backend.domain.outline_review import OutlineIssue, OutlineReview
from backend.domain.report_plan import ReportPlan
from backend.domain.strategy import ReportStrategy
from backend.model_providers.base import LlmError, generate_structured


class OutlineCriticAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(self, plan: ReportPlan, strategy: ReportStrategy) -> OutlineReview:
        if self.llm_mode == "offline":
            return _offline_review(plan)
        try:
            instruction = load_agent_instruction("outline_critic")
            user = (
                "Review this outline and return OutlineReview JSON.\n"
                "Flag duplicated, raw OCR-like, sentence-fragment, or weak top-level headings.\n\n"
                f"{json.dumps({'strategy': strategy.model_dump(), 'plan': plan.model_dump()}, ensure_ascii=False)}"
            )
            return generate_structured(
                OutlineReview,
                instruction,
                user,
                agent_name="report_planner",
                max_retries=1,
            )
        except LlmError:
            return _offline_review(plan)


def _offline_review(plan: ReportPlan) -> OutlineReview:
    bad = [n for n in plan.outline if "..." in n.title]
    issues = [
        OutlineIssue(
            issue_id=f"OUT-{i+1:03d}",
            severity=IssueSeverity.MAJOR,
            issue_type="ELLIPSIS_TITLE",
            node_id=n.node_id,
            description=f"제목에 말줄임표가 포함됨: {n.title}",
            recommendation="완전한 명사구 제목으로 교체",
        )
        for i, n in enumerate(bad)
    ]
    return OutlineReview(
        decision=ReviewDecision.REVISE if issues else ReviewDecision.PASS,
        issues=issues,
        summary="offline critic",
    )
