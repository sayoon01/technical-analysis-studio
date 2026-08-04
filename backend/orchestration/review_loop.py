"""Review–Revise loop with parallel reviewers and quality gate."""

from __future__ import annotations

import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from backend.agents.editorial_reviewer.agent import EditorialReviewerAgent
from backend.agents.reviser.agent import ReviserAgent
from backend.agents.technical_reviewer.agent import TechnicalReviewerAgent
from backend.config import settings
from backend.domain.chapter import ChapterDraft, DraftParagraph, SubsectionDraft
from backend.domain.enums import ProjectStage, ReviewDecision
from backend.domain.evidence import EvidencePack
from backend.orchestration.quality_gate import can_finalize, requires_manual_review
from backend.skills.analysis.claim_extractor import extract_claims
from backend.skills.analysis.draft_validator import validate_draft
from backend.storage.edition_repository import (
    ChapterRepository,
    ClaimRepository,
    EditionRepository,
    EvidencePackRepository,
    SectionRepository,
)
from backend.storage.repositories import ProjectRepository
from backend.storage.review_repository import ReviewRepository


class ReviewLoop:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
        max_revisions: int | None = None,
    ) -> None:
        self.conn = conn
        self.llm_mode = llm_mode
        self.max_revisions = max_revisions or settings.max_revisions
        self.projects = ProjectRepository(conn)
        self.editions = EditionRepository(conn)
        self.sections = SectionRepository(conn)
        self.packs = EvidencePackRepository(conn)
        self.claims = ClaimRepository(conn)
        self.chapters = ChapterRepository(conn)
        self.reviews = ReviewRepository(conn)
        self.technical = TechnicalReviewerAgent(llm_mode=llm_mode)
        self.editorial = EditorialReviewerAgent(llm_mode=llm_mode)
        self.reviser = ReviserAgent(llm_mode=llm_mode)

    def run_edition(self, edition_id: str) -> dict:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        project_id = edition["project_id"]
        self.projects.update_stage(project_id, ProjectStage.REVIEWING.value)

        results = []
        all_pass = True
        manual = False
        for section in self.sections.list_for_edition(edition_id):
            outcome = self.run_section(section["section_id"])
            results.append(outcome)
            if outcome["status"] != "PASSED":
                all_pass = False
            if outcome["status"] == "MANUAL_REVIEW":
                manual = True

        full_report = None
        if all_pass:
            full_report = self.run_full_report(edition_id)
            if full_report["status"] != "PASSED":
                all_pass = False

        if all_pass:
            self.editions.update_status(edition_id, "FINALIZING")
            self.projects.update_stage(project_id, ProjectStage.FINALIZING.value)
            # Phase 4: mark ready for export without full finalization pipeline yet
            self.editions.update_status(edition_id, "READY")
            self.projects.update_stage(project_id, ProjectStage.READY_FOR_EXPORT.value)
            stage = ProjectStage.READY_FOR_EXPORT.value
        elif manual:
            self.editions.update_status(edition_id, "IN_REVIEW")
            stage = ProjectStage.REVIEWING.value
        else:
            self.editions.update_status(edition_id, "IN_REVIEW")
            stage = ProjectStage.REVIEWING.value

        return {
            "edition_id": edition_id,
            "stage": stage,
            "all_passed": all_pass,
            "manual_review": manual,
            "sections": results,
            "full_report": full_report,
        }

    def run_full_report(self, edition_id: str) -> dict:
        sections = self.sections.list_for_edition(edition_id)
        if not sections:
            raise ValueError("No sections in edition")
        merged = "\n\n---\n\n".join((s.get("content_markdown") or "").strip() for s in sections)
        synthetic_section_id = f"FULL-{edition_id}"
        editorial = self.editorial.run(
            section_id=synthetic_section_id,
            markdown=merged,
            scope="FULL_REPORT",
        )
        self.reviews.save_editorial_full_report(edition_id, editorial)
        if editorial.decision == ReviewDecision.PASS:
            return {"edition_id": edition_id, "status": "PASSED", "issues": []}
        return {
            "edition_id": edition_id,
            "status": "REVISE",
            "issues": [i.model_dump(mode="json") for i in editorial.issues],
        }

    def run_section(self, section_id: str) -> dict:
        section = self.sections.get(section_id)
        if not section:
            raise KeyError(section_id)

        pack_row = None
        if section.get("evidence_pack_id"):
            pack_row = self.packs.get(section["evidence_pack_id"])
        if not pack_row:
            pack_row = self.packs.get_for_section(section_id)
        if not pack_row:
            raise ValueError(f"No evidence pack for section {section_id}")

        pack = EvidencePack.model_validate(pack_row["pack"])
        revision = int(section.get("revision_count") or 1)
        history = []
        chapter_key = section.get("outline_node_id") or section_id
        chapter_row = self.chapters.get_by_key(section["edition_id"], chapter_key)
        chapter_id = chapter_row["chapter_id"] if chapter_row else f"CH-{chapter_key}"

        while True:
            self.projects.update_stage(
                self.editions.get(section["edition_id"])["project_id"],
                ProjectStage.REVIEWING.value,
            )
            markdown = section["content_markdown"] or ""
            claims = self.claims.list_for_section(section_id)
            draft = self.chapters.load_draft(chapter_id)

            # 1) Deterministic draft validator (before LLM reviewers)
            draft_validation = validate_draft(
                section_id=section_id,
                markdown=markdown,
                pack=pack,
                draft=draft,
            )

            # 2) Parallel technical + editorial reviewers
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_t = pool.submit(
                    self.technical.run,
                    section_id=section_id,
                    markdown=markdown,
                    pack=pack,
                    claims=claims,
                )
                fut_e = pool.submit(
                    self.editorial.run,
                    section_id=section_id,
                    markdown=markdown,
                )
                technical = fut_t.result()
                editorial = fut_e.result()

            # Merge deterministic blockers into technical review
            if draft_validation.issues:
                technical.issues = list(technical.issues) + list(draft_validation.issues)
                technical.critical_issue_count = max(
                    technical.critical_issue_count,
                    sum(
                        1
                        for i in draft_validation.issues
                        if i.severity.value == "CRITICAL"
                    ),
                )
                if not draft_validation.ok and technical.decision == ReviewDecision.PASS:
                    technical.decision = ReviewDecision.REVISE

            self.reviews.save_technical(section_id, technical)
            self.reviews.save_editorial(section_id, editorial)

            round_info = {
                "revision": revision,
                "technical_decision": technical.decision.value,
                "editorial_decision": editorial.decision.value,
                "unsupported": technical.unsupported_claim_count,
                "numeric_mismatch": technical.numeric_mismatch_count,
                "citation_mismatch": technical.citation_mismatch_count,
                "draft_ok": draft_validation.ok,
                "internal_markers": draft_validation.internal_marker_count,
            }
            history.append(round_info)

            if can_finalize(technical, editorial, draft_validation=draft_validation):
                self.sections.update(section_id, status="PASSED")
                self.chapters.update_status(chapter_id, "PASSED")
                return {
                    "section_id": section_id,
                    "status": "PASSED",
                    "revision": revision,
                    "history": history,
                }

            if requires_manual_review(
                technical, editorial, revision, self.max_revisions
            ):
                self.sections.update(section_id, status="MANUAL_REVIEW")
                self.chapters.update_status(chapter_id, "MANUAL_REVIEW")
                return {
                    "section_id": section_id,
                    "status": "MANUAL_REVIEW",
                    "revision": revision,
                    "history": history,
                    "open_issues": self.reviews.open_issues(section_id),
                }

            # 3) Revise
            self.projects.update_stage(
                self.editions.get(section["edition_id"])["project_id"],
                ProjectStage.REVISING.value,
            )
            self.sections.update(section_id, status="REVISING")
            revision += 1
            result = self.reviser.run(
                title=section["title"],
                objective=section.get("objective") or "",
                markdown=markdown,
                pack=pack,
                technical=technical,
                editorial=editorial,
                revision=revision,
            )
            self.reviews.mark_issues_resolved(result.resolved_issue_ids)

            # Refresh claims from revised content
            self.claims.delete_for_section(section_id)
            for claim, eids in extract_claims(
                edition_id=section["edition_id"],
                section_id=section_id,
                markdown=result.updated_content,
                pack=pack,
            ):
                self.claims.save_claim(claim.model_dump(), eids)

            self.sections.save_version(
                section_id,
                revision,
                result.updated_content,
                f"revision {revision}: {len(result.changes)} changes",
            )
            section = self.sections.update(
                section_id,
                content_markdown=result.updated_content,
                revision_count=revision,
                status="DRAFT",
            )

            # Persist revised structured chapter when v2 tables exist
            revised_draft = _draft_from_markdown(
                chapter_id=chapter_id,
                title=section["title"],
                markdown=result.updated_content,
                previous=draft,
            )
            self.chapters.save_chapter_draft(
                edition_id=section["edition_id"],
                section_id=section_id,
                order_index=int(chapter_row["order_index"]) if chapter_row else 0,
                chapter_key=chapter_key,
                draft=revised_draft,
                body_markdown=result.updated_content,
                summary=f"revision {revision}",
            )
            chapter_row = self.chapters.get_by_key(section["edition_id"], chapter_key)


def _draft_from_markdown(
    *,
    chapter_id: str,
    title: str,
    markdown: str,
    previous: ChapterDraft | None,
) -> ChapterDraft:
    chunks = [c.strip() for c in re.split(r"\n\s*\n", markdown or "") if c.strip()]
    paras: list[DraftParagraph] = []
    for i, chunk in enumerate(chunks, start=1):
        if chunk.startswith("#"):
            continue
        text = re.sub(r"<!--[\s\S]*?-->", "", chunk).strip()
        if not text:
            continue
        paras.append(
            DraftParagraph(
                paragraph_id=f"PAR-{chapter_id}-{i:03d}",
                paragraph_type="ANALYSIS",
                text=text,
                evidence_ids=[],
            )
        )
    if not paras and previous:
        return previous
    return ChapterDraft(
        chapter_id=chapter_id,
        title=title,
        lead=previous.lead if previous else "",
        subsections=[
            SubsectionDraft(
                subsection_id=f"SUB-{chapter_id}-01",
                title=title,
                paragraphs=paras,
            )
        ],
        visual_intents=list(previous.visual_intents) if previous else [],
        limitations=list(previous.limitations) if previous else [],
        key_takeaways=list(previous.key_takeaways) if previous else [],
        chapter_conclusion=previous.chapter_conclusion if previous else None,
    )
