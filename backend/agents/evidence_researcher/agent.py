"""EvidenceResearcherAgent.

Code builds the EvidencePack (retrieval + structured facts). The LLM never
regenerates the full pack — optional small EvidenceRefineDelta only.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.evidence import EvidencePack, EvidenceRefineDelta
from backend.model_providers.base import LlmError, generate_structured
from backend.skills.retrieval.evidence_builder import build_evidence_pack
from backend.skills.retrieval.evidence_refine import (
    apply_evidence_refine_delta,
    evidence_catalog_for_llm,
)

logger = logging.getLogger(__name__)


def _refine_mode() -> str:
    """off | delta — default off (retrieval pack → writer)."""
    raw = (
        os.getenv("TAS_EVIDENCE_REFINE", getattr(settings, "evidence_refine_mode", "off"))
        or "off"
    )
    return str(raw).lower().strip()


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

        # Refine is quality enhancement only — never block production.
        if self.llm_mode == "offline" or _refine_mode() != "delta":
            return pack

        try:
            return self._apply_delta_refine(
                pack,
                section_id=section_id,
                title=title,
                objective=objective,
            )
        except Exception as e:
            logger.warning(
                "evidence refine delta skipped section=%s err=%s", section_id, e
            )
            return pack

    def _apply_delta_refine(
        self,
        pack: EvidencePack,
        *,
        section_id: str,
        title: str,
        objective: str,
    ) -> EvidencePack:
        catalog = evidence_catalog_for_llm(pack)
        if not catalog:
            return pack

        instruction = load_agent_instruction("evidence_researcher")
        user = {
            "section_id": section_id,
            "title": title,
            "objective": objective,
            "research_questions": pack.research_questions,
            "candidates": catalog,
            "instructions": (
                "Select/rank/drop by id only. Do not invent ids, pages, or statements. "
                "Return EvidenceRefineDelta JSON only."
            ),
        }
        try:
            delta = generate_structured(
                EvidenceRefineDelta,
                instruction,
                json.dumps(user, ensure_ascii=False)[:14000],
                agent_name="evidence_researcher",
                max_retries=1,
            )
        except LlmError as e:
            logger.warning("evidence refine LLM failed section=%s err=%s", section_id, e)
            return pack

        return apply_evidence_refine_delta(pack, delta)
