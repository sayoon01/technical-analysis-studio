"""Edition / section application service."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.orchestration.edition_diff import EditionDiffer
from backend.orchestration.impact_analyzer import ImpactAnalyzer
from backend.orchestration.production_pipeline import ProductionPipeline
from backend.orchestration.review_loop import ReviewLoop
from backend.services.job_status import lock_for, set_job
from backend.storage.edition_repository import (
    ClaimRepository,
    EditionRepository,
    EvidencePackRepository,
    SectionRepository,
)
from backend.storage.repositories import (
    ContentBlockRepository,
    PageRepository,
    ProjectRepository,
    SourceRepository,
)


class EditionService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
        vector_root: Path | None = None,
    ) -> None:
        self.conn = conn
        self.editions = EditionRepository(conn)
        self.sections = SectionRepository(conn)
        self.claims = ClaimRepository(conn)
        self.packs = EvidencePackRepository(conn)
        self.pages = PageRepository(conn)
        self.blocks = ContentBlockRepository(conn)
        self.projects = ProjectRepository(conn)
        self.sources = SourceRepository(conn)
        self.pipeline = ProductionPipeline(
            conn, llm_mode=llm_mode, vector_root=vector_root
        )
        self.review_loop = ReviewLoop(conn, llm_mode=llm_mode)
        self.impact = ImpactAnalyzer(conn)
        self.differ = EditionDiffer(conn)

    def produce(
        self,
        project_id: str,
        parent_edition_id: str | None = None,
        *,
        auto_review: bool = True,
        new_source_ids: list[str] | None = None,
        resume_edition_id: str | None = None,
    ) -> dict:
        lock = lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("Production already running for this project")
        set_job(project_id, "producing")
        try:
            if resume_edition_id:
                result = self.pipeline.run_resume(project_id, resume_edition_id)
            elif parent_edition_id:
                result = self.improve(
                    project_id,
                    parent_edition_id,
                    new_source_ids=new_source_ids,
                )
            else:
                result = self.pipeline.run(project_id, parent_edition_id=None)
            if auto_review and result.get("edition_id"):
                set_job(project_id, "reviewing")
                review = self.review_loop.run_edition(result["edition_id"])
                result["review"] = {
                    "stage": review.get("stage"),
                    "all_passed": review.get("all_passed"),
                    "manual_review": review.get("manual_review"),
                }
                result["stage"] = review.get("stage") or result.get("stage")
            return result
        finally:
            set_job(project_id, None)
            lock.release()

    def resume(self, edition_id: str, *, auto_review: bool = True) -> dict:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        return self.produce(
            edition["project_id"],
            resume_edition_id=edition_id,
            auto_review=auto_review,
        )

    def improve(
        self,
        project_id: str,
        parent_edition_id: str,
        *,
        new_source_ids: list[str] | None = None,
    ) -> dict:
        return self.pipeline.run_incremental(
            project_id,
            parent_edition_id=parent_edition_id,
            new_source_ids=new_source_ids,
        )

    def preview_impact(
        self,
        project_id: str,
        parent_edition_id: str,
        *,
        new_source_ids: list[str] | None = None,
    ) -> dict:
        parent = self.editions.get(parent_edition_id)
        if not parent or parent["project_id"] != project_id:
            raise KeyError(parent_edition_id)
        all_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        parent_snap = [
            r["source_id"]
            for r in self.conn.execute(
                "SELECT source_id FROM corpus_snapshot_sources WHERE snapshot_id = ?",
                (parent["corpus_snapshot_id"],),
            ).fetchall()
        ]
        if new_source_ids is None:
            new_source_ids = [s for s in all_ids if s not in set(parent_snap)]
        report = self.impact.analyze(
            parent_edition_id=parent_edition_id,
            new_source_ids=new_source_ids,
            all_evidence_source_ids=all_ids,
        )
        return {
            "parent_edition_id": parent_edition_id,
            "new_source_ids": new_source_ids,
            "impacts": [
                {
                    "section_id": i.section_id,
                    "decision": i.decision.value,
                    "reasons": i.reasons,
                    "affected_claim_ids": i.affected_claim_ids,
                }
                for i in report.section_impacts
            ],
            "claim_relations": report.claim_relations,
        }

    def diff_editions(self, left_id: str, right_id: str) -> dict:
        if not self.editions.get(left_id) or not self.editions.get(right_id):
            raise KeyError("edition")
        return self.differ.diff(left_id, right_id)

    def list_editions(self, project_id: str) -> list[dict]:
        return self.editions.list_for_project(project_id)

    def get_edition(self, edition_id: str) -> dict:
        row = self.editions.get(edition_id)
        if not row:
            raise KeyError(edition_id)
        row = dict(row)
        row["sections"] = self.sections.list_for_edition(edition_id)
        return row

    def list_sections(self, edition_id: str) -> list[dict]:
        return self.sections.list_for_edition(edition_id)

    def get_section(self, section_id: str) -> dict:
        row = self.sections.get(section_id)
        if not row:
            raise KeyError(section_id)
        d = dict(row)
        d["claims"] = self.claims.list_for_section(section_id)
        pack = None
        if d.get("evidence_pack_id"):
            pack = self.packs.get(d["evidence_pack_id"])
        d["evidence_pack"] = pack["pack"] if pack else None
        d["citation_targets"] = self._citation_targets(d["claims"])
        return d

    def get_section_evidence(self, section_id: str) -> dict:
        section = self.sections.get(section_id)
        if not section:
            raise KeyError(section_id)
        pack = self.packs.get_for_section(section_id)
        return {
            "section_id": section_id,
            "evidence_pack": pack["pack"] if pack else None,
        }

    def list_versions(self, section_id: str) -> list[dict]:
        if not self.sections.get(section_id):
            raise KeyError(section_id)
        return self.sections.list_versions(section_id)

    def regenerate_section(self, project_id: str, section_id: str) -> dict:
        section = self.sections.get(section_id)
        if not section:
            raise KeyError(section_id)
        return self.pipeline.produce_section(
            project_id, section["edition_id"], section_id
        )

    def resolve_claim_location(self, claim_id: str) -> dict:
        claim = self.claims.get_claim(claim_id)
        if not claim:
            raise KeyError(claim_id)
        locations = []
        for ev in claim.get("evidence") or []:
            page = self.pages.get(ev["source_id"], ev["page"])
            try:
                block_ids = json.loads(ev.get("block_ids_json") or "[]")
            except Exception:
                block_ids = []
            all_blocks = self.blocks.list_for_source(ev["source_id"], ev["page"])
            if block_ids:
                blocks = [b for b in all_blocks if b["block_id"] in block_ids]
            else:
                blocks = all_blocks[:3]
            locations.append(
                {
                    "evidence_id": ev["evidence_id"],
                    "source_id": ev["source_id"],
                    "page": ev["page"],
                    "statement": ev["statement"],
                    "page_meta": page,
                    "blocks": [
                        {
                            "block_id": b["block_id"],
                            "text": b["text"],
                            "bbox": b["bbox"],
                        }
                        for b in blocks
                    ],
                    "image_path": page.get("image_path") if page else None,
                }
            )
        return {
            "claim_id": claim_id,
            "statement": claim["statement"],
            "locations": locations,
        }

    def _citation_targets(self, claims: list[dict]) -> list[dict]:
        out = []
        for c in claims:
            for ev in c.get("evidence") or []:
                out.append(
                    {
                        "claim_id": c["claim_id"],
                        "source_id": ev["source_id"],
                        "page": ev["page"],
                        "evidence_id": ev["evidence_id"],
                    }
                )
        return out
