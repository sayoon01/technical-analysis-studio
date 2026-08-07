"""EditorialReviewerAgent — structure / clarity / consistency only.

Independent of TechnicalReviewer judgment. No silent offline fallback.
"""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.review import EditorialReview
from backend.model_providers.base import LlmError, generate_structured
from backend.skills.analysis.review_offline import review_editorial_offline


class EditorialReviewerAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        *,
        section_id: str,
        markdown: str,
        scope: str = "CHAPTER",
    ) -> EditorialReview:
        base = review_editorial_offline(
            section_id=section_id,
            markdown=markdown,
            scope=scope,
        )
        if self.llm_mode == "offline":
            return base.model_copy(update={"provenance": "offline"})
        try:
            instruction = load_agent_instruction("editorial_reviewer")
            user = json.dumps(
                {
                    "section_id": section_id,
                    "scope": scope,
                    "markdown": markdown[:12000],
                    "deterministic_findings": base.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
            refined = generate_structured(
                EditorialReview,
                instruction,
                user,
                agent_name="editorial_reviewer",
            )
            refined.critical_issue_count = max(
                refined.critical_issue_count, base.critical_issue_count
            )
            if base.issues and not refined.issues:
                refined.issues = base.issues
            refined.provenance = "online"
            return refined
        except LlmError:
            raise
        except Exception as exc:
            raise LlmError(f"EditorialReviewer failed: {exc}") from exc
