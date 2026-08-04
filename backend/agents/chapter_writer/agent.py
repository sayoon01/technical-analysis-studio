"""ChapterWriterAgent returning ChapterDraft JSON."""

from __future__ import annotations

import json
import re

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.chapter import ChapterDraft, DraftParagraph, SubsectionDraft, VisualIntent
from backend.domain.evidence import EvidencePack
from backend.model_providers.base import LlmError, allow_offline_fallback, call_ollama_json
from backend.skills.analysis.section_writer import write_section_offline


class ChapterWriterAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        *,
        chapter_id: str,
        title: str,
        objective: str,
        pack: EvidencePack,
        plan_title: str | None = None,
        prev_summary: str | None = None,
        next_objective: str | None = None,
        format_notes: str | None = None,
    ) -> ChapterDraft:
        if self.llm_mode == "offline":
            return _offline_chapter_draft(
                chapter_id=chapter_id,
                title=title,
                objective=objective,
                pack=pack,
            )

        try:
            instruction = load_agent_instruction("chapter_writer")
            user = {
                "plan_title": plan_title,
                "chapter_id": chapter_id,
                "chapter_title": title,
                "objective": objective,
                "prev_summary": prev_summary,
                "next_objective": next_objective,
                "format_notes": format_notes,
                "evidence_pack": pack.model_dump(),
            }
            from backend.model_providers.registry import agent_model_config
            from backend.config import settings as cfg
            from backend.model_providers.base import resolve_ollama_model

            acfg = agent_model_config("chapter_writer")
            raw = call_ollama_json(
                instruction + "\n\nReturn JSON: {\"chapter_draft\": {...ChapterDraft...}}",
                json.dumps(user, ensure_ascii=False)[:28000],
                model=resolve_ollama_model("chapter_writer") or cfg.ollama_model,
                temperature=float(acfg.get("temperature", 0.2)),
            )
            payload = raw.get("chapter_draft") or raw.get("draft") or raw
            draft = ChapterDraft.model_validate(payload)
            if not draft.subsections:
                if not allow_offline_fallback():
                    raise LlmError("ChapterWriter returned empty subsections")
                return _offline_chapter_draft(
                    chapter_id=chapter_id,
                    title=title,
                    objective=objective,
                    pack=pack,
                )
            return draft
        except Exception:
            if not allow_offline_fallback():
                raise
            return _offline_chapter_draft(
                chapter_id=chapter_id,
                title=title,
                objective=objective,
                pack=pack,
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
