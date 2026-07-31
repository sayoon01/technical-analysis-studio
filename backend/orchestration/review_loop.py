"""Review–Revise loop with parallel reviewers and quality gate."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from backend.agents.editorial_reviewer.agent import EditorialReviewerAgent
from backend.agents.reviser.agent import ReviserAgent
from backend.agents.technical_reviewer.agent import TechnicalReviewerAgent
from backend.config import settings
from backend.domain.enums import ProjectStage
from backend.domain.evidence import EvidencePack
from backend.orchestration.quality_gate import can_finalize, requires_manual_review
from backend.skills.analysis.claim_extractor import extract_claims
from backend.storage.edition_repository import (
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

        while True:
            self.projects.update_stage(
                self.editions.get(section["edition_id"])["project_id"],
                ProjectStage.REVIEWING.value,
            )
            markdown = section["content_markdown"] or ""
            claims = self.claims.list_for_section(section_id)

            # Parallel reviewers
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

            self.reviews.save_technical(section_id, technical)
            self.reviews.save_editorial(section_id, editorial)

            round_info = {
                "revision": revision,
                "technical_decision": technical.decision.value,
                "editorial_decision": editorial.decision.value,
                "unsupported": technical.unsupported_claim_count,
                "numeric_mismatch": technical.numeric_mismatch_count,
                "citation_mismatch": technical.citation_mismatch_count,
            }
            history.append(round_info)

            if can_finalize(technical, editorial):
                self.sections.update(section_id, status="PASSED")
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
                return {
                    "section_id": section_id,
                    "status": "MANUAL_REVIEW",
                    "revision": revision,
                    "history": history,
                    "open_issues": self.reviews.open_issues(section_id),
                }

            # Revise
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
