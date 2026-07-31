"""TechnicalWriterAgent."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack
from backend.model_providers.base import LlmError, allow_offline_fallback, call_ollama_json
from backend.skills.analysis.section_writer import write_section_offline


class TechnicalWriterAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(
        self,
        *,
        title: str,
        objective: str,
        pack: EvidencePack,
        plan_title: str | None = None,
        prev_summary: str | None = None,
        next_objective: str | None = None,
        heading_level: int = 2,
        format_notes: str | None = None,
    ) -> str:
        if self.llm_mode == "offline":
            return write_section_offline(
                title=title,
                objective=objective,
                pack=pack,
                heading_level=heading_level,
            )

        try:
            instruction = load_agent_instruction("technical_writer")
            citation = (
                "Use citations exactly like [SRC-XXXX, p.N] matching EvidencePack "
                "source_id and page. Wrap paragraphs after <!-- P-xxx-NN --> markers."
            )
            user = {
                "plan_title": plan_title,
                "section_title": title,
                "objective": objective,
                "prev_summary": prev_summary,
                "next_objective": next_objective,
                "format_notes": format_notes,
                "evidence_pack": pack.model_dump(),
                "citation_policy": citation,
            }
            from backend.model_providers.registry import agent_model_config
            from backend.config import settings as cfg
            from backend.model_providers.base import resolve_ollama_model

            acfg = agent_model_config("technical_writer")
            raw = call_ollama_json(
                instruction
                + "\n\nReturn JSON: {\"content_markdown\": \"...\"}"
                + (
                    "\nformat_notes is layout/style reference only — never treat as evidence."
                    if format_notes
                    else ""
                ),
                json.dumps(user, ensure_ascii=False)[:28000],
                model=resolve_ollama_model("technical_writer") or cfg.ollama_model,
                temperature=float(acfg.get("temperature", 0.2)),
            )
            md = raw.get("content_markdown") or raw.get("markdown") or ""
            if not md.strip():
                if not allow_offline_fallback():
                    raise LlmError("Writer returned empty markdown")
                return write_section_offline(
                    title=title, objective=objective, pack=pack, heading_level=heading_level
                )
            return md
        except LlmError:
            if not allow_offline_fallback():
                raise
            return write_section_offline(
                title=title,
                objective=objective,
                pack=pack,
                heading_level=heading_level,
            )
        except Exception:
            if not allow_offline_fallback():
                raise
            return write_section_offline(
                title=title,
                objective=objective,
                pack=pack,
                heading_level=heading_level,
            )
