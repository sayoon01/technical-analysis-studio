"""Chapter-aware EvidencePack service (deterministic)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.domain.evidence import EvidencePack
from backend.services.report_blueprint_service import ChapterBlueprintUnit
from backend.skills.retrieval.evidence_builder import build_evidence_pack


class EvidencePackService:
    def __init__(self, conn: sqlite3.Connection, *, vector_root: Path | None = None) -> None:
        self.conn = conn
        self.vector_root = vector_root

    def build_for_chapter(
        self,
        *,
        project_id: str,
        section_id: str,
        title: str,
        objective: str,
        chapter: ChapterBlueprintUnit | None,
        research_questions: list[str] | None,
        required_evidence_types: list[str] | None,
        source_ids: list[str] | None,
        previous_section_content: str | None = None,
    ) -> EvidencePack:
        questions = list(research_questions or [])
        if chapter:
            questions = list(dict.fromkeys([*chapter.questions_to_answer, *questions]))
            if chapter.core_message:
                questions = [chapter.core_message, *questions]

        pack = build_evidence_pack(
            self.conn,
            project_id=project_id,
            section_id=section_id,
            section_objective=objective,
            title=title,
            research_questions=questions,
            required_evidence_types=required_evidence_types,
            source_ids=source_ids,
            vector_root=self.vector_root,
        )
        pack.previous_section_content = previous_section_content
        if previous_section_content:
            pack.reuse_decision = "STYLE_ONLY"
        return pack
