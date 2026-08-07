"""ChapterWriterAgent — Canonical Owner for chapter body reasoning.

Input: ChapterWritingContext (assembled outside the agent)
Output: ChapterDraft
Does not retrieve evidence, mutate outline, review, or persist.
"""

from __future__ import annotations

import json
import re

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.chapter import (
    ChapterDraft,
    ChapterWritingContext,
    DraftParagraph,
    SubsectionDraft,
    VisualIntent,
)
from backend.domain.evidence import EvidencePack
from backend.model_providers.base import LlmError, allow_offline_fallback, generate_structured
from backend.skills.analysis.section_writer import write_section_offline


class ChapterWriterAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(self, ctx: ChapterWritingContext) -> ChapterDraft:
        if self.llm_mode == "offline":
            return _offline_chapter_draft(
                chapter_id=ctx.chapter_id,
                title=ctx.title,
                objective=ctx.objective,
                pack=ctx.evidence_pack,
            )

        try:
            instruction = load_agent_instruction("chapter_writer")
            user = _user_payload(ctx)
            draft = generate_structured(
                ChapterDraft,
                instruction,
                json.dumps(user, ensure_ascii=False)[:28000],
                agent_name="chapter_writer",
                max_retries=1,
            )
            draft = _align_draft_identity(draft, ctx)
            if not draft.subsections:
                if not allow_offline_fallback():
                    raise LlmError("ChapterWriter returned empty subsections")
                return _offline_chapter_draft(
                    chapter_id=ctx.chapter_id,
                    title=ctx.title,
                    objective=ctx.objective,
                    pack=ctx.evidence_pack,
                )
            return draft
        except Exception:
            if not allow_offline_fallback():
                raise
            return _offline_chapter_draft(
                chapter_id=ctx.chapter_id,
                title=ctx.title,
                objective=ctx.objective,
                pack=ctx.evidence_pack,
            )


def render_chapter_markdown(draft: ChapterDraft, *, heading_level: int = 2) -> str:
    h = "#" * max(1, min(6, heading_level))
    lines: list[str] = [f"{h} {draft.title}", ""]
    if draft.lead.strip():
        lines.append(draft.lead.strip())
        lines.append("")
    for sub in draft.subsections:
        lines.append(f"{h}# {sub.title}")
        lines.append("")
        for p in sub.paragraphs:
            text = _strip_internal_markers(p.text)
            if text:
                lines.append(text)
                lines.append("")
    if draft.chapter_conclusion:
        lines.append(f"{h}# 결론")
        lines.append("")
        lines.append(_strip_internal_markers(draft.chapter_conclusion))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _user_payload(ctx: ChapterWritingContext) -> dict:
    """Serialize Writing Context for the model; keep evidence detailed."""
    data = ctx.model_dump(mode="json")
    # Bound format notes / previous summary; Evidence Pack stays authoritative.
    if data.get("format_notes") and len(str(data["format_notes"])) > 3000:
        data["format_notes"] = str(data["format_notes"])[:3000]
    if data.get("prev_summary") and len(str(data["prev_summary"])) > 600:
        data["prev_summary"] = str(data["prev_summary"])[:600]
    return data


def _align_draft_identity(draft: ChapterDraft, ctx: ChapterWritingContext) -> ChapterDraft:
    if not draft.chapter_id:
        draft.chapter_id = ctx.chapter_id
    if not draft.title:
        draft.title = ctx.title
    return draft


def _offline_chapter_draft(
    *, chapter_id: str, title: str, objective: str, pack: EvidencePack
) -> ChapterDraft:
    md = write_section_offline(
        title=title,
        objective=objective,
        pack=pack,
        heading_level=2,
    )
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", md) if p.strip()]
    para_objs: list[DraftParagraph] = []
    for i, p in enumerate(paragraphs, start=1):
        para_objs.append(
            DraftParagraph(
                paragraph_id=f"PAR-{chapter_id}-{i:03d}",
                paragraph_type="FACT" if i == 1 else "ANALYSIS",
                text=_strip_internal_markers(p),
                evidence_ids=[],
            )
        )
    visual_intents: list[VisualIntent] = []
    if pack.metrics:
        visual_intents.append(
            VisualIntent(
                visual_type="COMPARISON_TABLE",
                purpose="핵심 정량 지표 요약",
                related_evidence_ids=[m.metric_id for m in pack.metrics[:4]],
            )
        )
    return ChapterDraft(
        chapter_id=chapter_id,
        title=title,
        lead=objective,
        subsections=[
            SubsectionDraft(
                subsection_id=f"SUB-{chapter_id}-01",
                title=title,
                paragraphs=para_objs,
            )
        ],
        chapter_conclusion=pack.limitations[0] if pack.limitations else None,
        key_takeaways=[],
        limitations=list(pack.limitations[:3]),
        visual_intents=visual_intents,
    )


def _strip_internal_markers(text: str) -> str:
    t = re.sub(r"<!--[\s\S]*?-->", "", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t
