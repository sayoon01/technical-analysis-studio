"""TechnicalReviewerAgent — technical accuracy / evidence grounding only.

No silent offline fallback: llm/adk failure raises. Explicit TAS_LLM_MODE=offline
uses deterministic review_technical_offline with provenance=offline.
"""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack
from backend.domain.review import TechnicalReview
from backend.model_providers.base import LlmError, generate_structured
from backend.skills.analysis.review_offline import review_technical_offline


class TechnicalReviewerAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        *,
        section_id: str,
        markdown: str,
        pack: EvidencePack,
        claims: list[dict] | None = None,
    ) -> TechnicalReview:
        base = review_technical_offline(
            section_id=section_id,
            markdown=markdown,
            pack=pack,
            claims=claims,
        )
        if self.llm_mode == "offline":
            return base.model_copy(update={"provenance": "offline"})
        try:
            instruction = load_agent_instruction("technical_reviewer")
            user = json.dumps(
                {
                    "section_id": section_id,
                    "markdown": markdown[:12000],
                    "evidence_pack": pack.model_dump(mode="json"),
                    "deterministic_findings": base.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
            refined = generate_structured(
                TechnicalReview,
                instruction,
                user,
                agent_name="technical_reviewer",
            )
            # Never loosen blockers below deterministic counts
            refined.unsupported_claim_count = max(
                refined.unsupported_claim_count, base.unsupported_claim_count
            )
            refined.citation_mismatch_count = max(
                refined.citation_mismatch_count, base.citation_mismatch_count
            )
            refined.numeric_mismatch_count = max(
                refined.numeric_mismatch_count, base.numeric_mismatch_count
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
            raise LlmError(f"TechnicalReviewer failed: {exc}") from exc
