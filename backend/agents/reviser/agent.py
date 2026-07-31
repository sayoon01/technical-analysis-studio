"""ReviserAgent."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack
from backend.domain.review import EditorialReview, RevisionResult, TechnicalReview
from backend.model_providers.base import LlmError, allow_offline_fallback, generate_structured
from backend.skills.analysis.revise_offline import revise_section_offline


class ReviserAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        *,
        title: str,
        objective: str,
        markdown: str,
        pack: EvidencePack,
        technical: TechnicalReview,
        editorial: EditorialReview,
        revision: int,
    ) -> RevisionResult:
        base = revise_section_offline(
            title=title,
            objective=objective,
            markdown=markdown,
            pack=pack,
            technical=technical,
            editorial=editorial,
            revision=revision,
        )
        if self.llm_mode == "offline":
            return base
        try:
            instruction = load_agent_instruction("reviser")
            user = json.dumps(
                {
                    "title": title,
                    "objective": objective,
                    "markdown": markdown[:12000],
                    "evidence_pack": pack.model_dump(mode="json"),
                    "technical_review": technical.model_dump(mode="json"),
                    "editorial_review": editorial.model_dump(mode="json"),
                    "revision": revision,
                },
                ensure_ascii=False,
            )
            refined = generate_structured(
                RevisionResult,
                instruction,
                user,
                agent_name="reviser",
            )
            if not (refined.updated_content or "").strip():
                return base
            refined.revision = revision
            return refined
        except LlmError:
            if not allow_offline_fallback():
                raise
            return base
        except Exception:
            if not allow_offline_fallback():
                raise
            return base
