"""ReviserAgent — targeted revision from aggregated issues only.

Does not search evidence, change outline, decide review verdict, or orchestrate DB.
No silent offline fallback.
"""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack
from backend.domain.review import EditorialReview, RevisionResult, ReviewIssue, TechnicalReview
from backend.model_providers.base import LlmError, generate_structured
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
        aggregated_issues: list[ReviewIssue] | None = None,
        locked_paragraph_texts: list[str] | None = None,
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
        if locked_paragraph_texts:
            base = base.model_copy(
                update={
                    "updated_content": _preserve_locked_snippets(
                        base.updated_content, locked_paragraph_texts
                    )
                }
            )
        if self.llm_mode == "offline":
            return base.model_copy(update={"provenance": "offline"})
        try:
            instruction = load_agent_instruction("reviser")
            payload = {
                "title": title,
                "objective": objective,
                "markdown": markdown[:12000],
                "evidence_pack": pack.model_dump(mode="json"),
                "technical_review": technical.model_dump(mode="json"),
                "editorial_review": editorial.model_dump(mode="json"),
                "revision": revision,
            }
            if aggregated_issues is not None:
                payload["aggregated_issues"] = [
                    i.model_dump(mode="json") for i in aggregated_issues
                ]
            if locked_paragraph_texts:
                payload["user_locked_paragraphs"] = locked_paragraph_texts
                payload["constraint"] = (
                    "Do not modify USER_LOCKED paragraph texts listed above."
                )
            user = json.dumps(payload, ensure_ascii=False)
            refined = generate_structured(
                RevisionResult,
                instruction,
                user,
                agent_name="reviser",
            )
            if not (refined.updated_content or "").strip():
                raise LlmError("Reviser returned empty content")
            if locked_paragraph_texts:
                refined.updated_content = _preserve_locked_snippets(
                    refined.updated_content, locked_paragraph_texts
                )
            refined.revision = revision
            refined.provenance = "online"
            return refined
        except LlmError:
            raise
        except Exception as exc:
            raise LlmError(f"Reviser failed: {exc}") from exc


def _preserve_locked_snippets(content: str, locked_texts: list[str]) -> str:
    """Ensure USER_LOCKED paragraph bodies remain present after revision.

    If a locked snippet was dropped, append it (paragraph-table lock is the
    primary contract; this is a markdown-level safety net).
    """
    out = content or ""
    missing = [t for t in locked_texts if t and t.strip() and t.strip() not in out]
    if not missing:
        return out
    appendix = "\n\n".join(t.strip() for t in missing)
    return (out.rstrip() + "\n\n" + appendix + "\n") if out.strip() else appendix + "\n"
