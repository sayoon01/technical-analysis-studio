"""EvidenceResearcherAgent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack
from backend.model_providers.base import LlmError, allow_offline_fallback, generate_structured
from backend.skills.retrieval.evidence_builder import build_evidence_pack


class EvidenceResearcherAgent:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
        vector_root: Path | None = None,
    ) -> None:
        self.conn = conn
        self.llm_mode = (llm_mode or settings.llm_mode).lower()
        self.vector_root = vector_root

    def run(
        self,
        *,
        project_id: str,
        section_id: str,
        title: str,
        objective: str,
        research_questions: list[str] | None = None,
        required_evidence_types: list[str] | None = None,
        source_ids: list[str] | None = None,
        previous_section_content: str | None = None,
    ) -> EvidencePack:
        pack = build_evidence_pack(
            self.conn,
            project_id=project_id,
            section_id=section_id,
            section_objective=objective,
            title=title,
            research_questions=research_questions,
            required_evidence_types=required_evidence_types,
            source_ids=source_ids,
            vector_root=self.vector_root,
        )
        pack.previous_section_content = previous_section_content
        if previous_section_content:
            pack.reuse_decision = "STYLE_ONLY"

        if self.llm_mode == "offline":
            return pack

        try:
            instruction = load_agent_instruction("evidence_researcher")
            user = (
                "Refine this EvidencePack. Keep only EVIDENCE_SOURCE facts. "
                "Do not invent pages. You may re-rank, drop weak items, fill missing_evidence.\n\n"
                f"{pack.model_dump_json()}"
            )
            refined = generate_structured(
                EvidencePack,
                instruction,
                user,
                agent_name="evidence_researcher",
            )
            refined.section_id = section_id
            refined.previous_section_content = previous_section_content
            return refined
        except LlmError:
            if not allow_offline_fallback():
                raise
            return pack
        except Exception:
            if not allow_offline_fallback():
                raise
            return pack
