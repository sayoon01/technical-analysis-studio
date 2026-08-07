"""Production pipeline: edition → research → write → claims (per section)."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from backend.agents.chapter_writer.agent import ChapterWriterAgent, render_chapter_markdown
from backend.domain.chapter import ReportMemory
from backend.domain.enums import ImpactDecision, ProjectStage, SourceRole
from backend.domain.evidence import EvidencePack
from backend.orchestration.impact_analyzer import ImpactAnalyzer
from backend.skills.analysis.claim_extractor import extract_claims
from backend.skills.analysis.corpus_context import _role_text_digest
from backend.skills.analysis.draft_validator import validate_draft
from backend.skills.analysis.inherit_scrubber import scrub_inherited_section
from backend.services.evidence_pack_service import EvidencePackService
from backend.services.report_blueprint_service import ReportBlueprintService
from backend.storage.edition_repository import (
    ClaimRepository,
    ChapterRepository,
    EditionRepository,
    EvidencePackRepository,
    SectionRepository,
)
from backend.storage.plan_repository import PlanRepository
from backend.storage.repositories import ProjectRepository, SourceRepository


class ProductionPipeline:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
        vector_root: Path | None = None,
    ) -> None:
        self.conn = conn
        self.llm_mode = llm_mode
        self.projects = ProjectRepository(conn)
        self.sources = SourceRepository(conn)
        self.plans = PlanRepository(conn)
        self.editions = EditionRepository(conn)
        self.sections = SectionRepository(conn)
        self.packs = EvidencePackRepository(conn)
        self.claims = ClaimRepository(conn)
        self.chapters = ChapterRepository(conn)
        self.evidence_packs = EvidencePackService(conn, vector_root=vector_root)
        self.blueprints = ReportBlueprintService()
        self.writer = ChapterWriterAgent(llm_mode=llm_mode)

    def run(self, project_id: str, *, parent_edition_id: str | None = None) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        if project["stage"] != ProjectStage.PRODUCING.value:
            raise ValueError(f"Project must be PRODUCING (got {project['stage']})")

        plan = self.plans.latest_plan(project_id)
        outline = self.plans.get_outline(project_id)
        if not plan or not outline:
            raise ValueError("Approved plan/outline required")
        if not outline.get("approved"):
            raise ValueError("Outline not approved")

        source_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        format_notes = _role_text_digest(
            self.conn, project_id, SourceRole.FORMAT_REFERENCE.value
        ) or None
        snapshot_id = self.editions.create_snapshot(project_id, source_ids)
        edition = self.editions.create_edition(
            project_id=project_id,
            corpus_snapshot_id=snapshot_id,
            report_plan_id=plan["plan_id"],
            outline_id=outline["outline_id"],
            parent_edition_id=parent_edition_id,
        )
        self.projects.patch(project_id, current_edition_id=edition["edition_id"])

        nodes = outline["nodes"]
        chapter_units = self.blueprints.build_from_outline(outline_nodes=nodes)
        chapter_by_node = {c.node_id: c for c in chapter_units}
        produced = []
        report_memory = ReportMemory()
        prev_summary = None
        for i, node in enumerate(nodes):
            next_node = nodes[i + 1] if i + 1 < len(nodes) else None
            section, report_memory = self._produce_section(
                project_id=project_id,
                edition_id=edition["edition_id"],
                node=node,
                source_ids=source_ids,
                plan=plan,
                chapter_units=chapter_units,
                report_memory=report_memory,
                prev_summary=prev_summary,
                next_title=next_node.get("title") if next_node else None,
                next_objective=next_node.get("objective") if next_node else None,
                format_notes=format_notes,
                chapter=chapter_by_node.get(node["node_id"]),
                node_order=i + 1,
            )
            produced.append(
                {
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "status": section["status"],
                }
            )
            prev_summary = (section.get("content_markdown") or "")[:400]

        self.editions.update_status(edition["edition_id"], "IN_REVIEW")
        # Phase 3 ends at draft sections ready for review; stage stays PRODUCING
        # until Phase 4 review loop — mark project REVIEWING for clarity
        self.projects.update_stage(project_id, ProjectStage.REVIEWING.value)

        return {
            "edition_id": edition["edition_id"],
            "edition_number": edition["edition_number"],
            "snapshot_id": snapshot_id,
            "sections": produced,
            "stage": ProjectStage.REVIEWING.value,
            "mode": "full",
        }

    def run_resume(self, project_id: str, edition_id: str) -> dict:
        """Continue an interrupted edition: skip complete DRAFT sections, rewrite the rest."""
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        edition = self.editions.get(edition_id)
        if not edition or edition["project_id"] != project_id:
            raise ValueError("Invalid edition_id for resume")

        plan = self.plans.latest_plan(project_id)
        outline = self.plans.get_outline(project_id)
        if not plan or not outline:
            raise ValueError("Approved plan/outline required")
        if not outline.get("approved"):
            raise ValueError("Outline not approved")

        if project["stage"] != ProjectStage.PRODUCING.value:
            self.projects.update_stage(project_id, ProjectStage.PRODUCING.value)

        self.projects.patch(project_id, current_edition_id=edition_id)
        if edition.get("status") != "PRODUCING":
            self.editions.update_status(edition_id, "PRODUCING")

        source_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        format_notes = _role_text_digest(
            self.conn, project_id, SourceRole.FORMAT_REFERENCE.value
        ) or None

        existing = self.sections.list_for_edition(edition_id)
        by_node = {s.get("outline_node_id"): s for s in existing if s.get("outline_node_id")}

        nodes = outline["nodes"]
        chapter_units = self.blueprints.build_from_outline(outline_nodes=nodes)
        chapter_by_node = {c.node_id: c for c in chapter_units}
        produced = []
        report_memory = ReportMemory()
        prev_summary = None
        skipped = 0
        rewritten = 0

        for i, node in enumerate(nodes):
            next_node = nodes[i + 1] if i + 1 < len(nodes) else None
            prior = by_node.get(node["node_id"])
            if prior and self._section_is_complete(prior):
                skipped += 1
                prev_summary = (prior.get("content_markdown") or "")[:400]
                report_memory = self._memory_from_skipped_section(
                    report_memory, prior, node
                )
                produced.append(
                    {
                        "section_id": prior["section_id"],
                        "title": prior.get("title") or node["title"],
                        "status": prior.get("status"),
                        "resumed": "skipped",
                    }
                )
                continue

            section, report_memory = self._produce_section(
                project_id=project_id,
                edition_id=edition_id,
                node=node,
                source_ids=source_ids,
                plan=plan,
                chapter_units=chapter_units,
                report_memory=report_memory,
                prev_summary=prev_summary,
                next_title=next_node.get("title") if next_node else None,
                next_objective=next_node.get("objective") if next_node else None,
                existing_section_id=prior["section_id"] if prior else None,
                format_notes=format_notes,
                chapter=chapter_by_node.get(node["node_id"]),
                node_order=i + 1,
            )
            rewritten += 1
            produced.append(
                {
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "status": section["status"],
                    "resumed": "rewritten" if prior else "created",
                }
            )
            prev_summary = (section.get("content_markdown") or "")[:400]
            by_node[node["node_id"]] = section

        self.editions.update_status(edition_id, "IN_REVIEW")
        self.projects.update_stage(project_id, ProjectStage.REVIEWING.value)

        return {
            "edition_id": edition_id,
            "edition_number": edition["edition_number"],
            "snapshot_id": edition.get("corpus_snapshot_id"),
            "sections": produced,
            "stage": ProjectStage.REVIEWING.value,
            "mode": "resume",
            "skipped": skipped,
            "rewritten": rewritten,
        }

    @staticmethod
    def _section_is_complete(section: dict) -> bool:
        status = (section.get("status") or "").upper()
        if status in {"RESEARCHING", "WRITING", "REVISING", "PENDING", "FAILED"}:
            return False
        md = (section.get("content_markdown") or "").strip()
        return len(md) >= 40

    def _memory_from_skipped_section(
        self, memory: ReportMemory, section: dict, node: dict
    ) -> ReportMemory:
        from backend.domain.chapter import ChapterDraft

        stub = ChapterDraft(
            chapter_id=f"CH-{node.get('node_id')}",
            title=section.get("title") or node.get("title") or "",
            lead="",
            key_takeaways=[],
            limitations=[],
        )
        return self.blueprints.extend_report_memory(
            memory,
            draft=stub,
            summary=(section.get("content_markdown") or "")[:400],
        )

    def run_incremental(
        self,
        project_id: str,
        *,
        parent_edition_id: str,
        new_source_ids: list[str] | None = None,
    ) -> dict:
        """Create Vn+1 from parent, rewriting only impacted sections."""
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        parent = self.editions.get(parent_edition_id)
        if not parent or parent["project_id"] != project_id:
            raise ValueError("Invalid parent_edition_id")

        plan = self.plans.latest_plan(project_id)
        outline = self.plans.get_outline(project_id)
        if not plan or not outline or not outline.get("approved"):
            raise ValueError("Approved plan/outline required")

        all_source_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        format_notes = _role_text_digest(
            self.conn, project_id, SourceRole.FORMAT_REFERENCE.value
        ) or None
        parent_snap_sources = [
            r["source_id"]
            for r in self.conn.execute(
                """
                SELECT source_id FROM corpus_snapshot_sources
                WHERE snapshot_id = ?
                """,
                (parent["corpus_snapshot_id"],),
            ).fetchall()
        ]
        if new_source_ids is None:
            new_source_ids = [s for s in all_source_ids if s not in set(parent_snap_sources)]

        self.projects.update_stage(project_id, ProjectStage.PRODUCING.value)

        analyzer = ImpactAnalyzer(self.conn)
        impact = analyzer.analyze(
            parent_edition_id=parent_edition_id,
            new_source_ids=new_source_ids,
            all_evidence_source_ids=all_source_ids,
        )
        decisions = {
            i.section_id: i for i in impact.section_impacts
        }

        snapshot_id = self.editions.create_snapshot(project_id, all_source_ids)
        edition = self.editions.create_edition(
            project_id=project_id,
            corpus_snapshot_id=snapshot_id,
            report_plan_id=plan["plan_id"],
            outline_id=outline["outline_id"],
            parent_edition_id=parent_edition_id,
        )
        self.projects.patch(project_id, current_edition_id=edition["edition_id"])

        parent_sections = self.sections.list_for_edition(parent_edition_id)
        parent_by_node = {s["outline_node_id"]: s for s in parent_sections}
        parent_by_title = {s["title"]: s for s in parent_sections}

        rewrite_decisions = {
            ImpactDecision.PARTIAL_REWRITE,
            ImpactDecision.FULL_REWRITE,
            ImpactDecision.ADD_SECTION,
        }
        light_decisions = {
            ImpactDecision.KEEP,
            ImpactDecision.UPDATE_CITATION,
            ImpactDecision.LIGHT_EDIT,
        }

        produced = []
        rewritten = 0
        kept = 0
        nodes = outline["nodes"]
        chapter_units = self.blueprints.build_from_outline(outline_nodes=nodes)
        chapter_by_node = {c.node_id: c for c in chapter_units}
        report_memory = ReportMemory()
        prev_summary = None
        for i, node in enumerate(nodes):
            next_node = nodes[i + 1] if i + 1 < len(nodes) else None
            parent_sec = parent_by_node.get(node["node_id"]) or parent_by_title.get(
                node["title"]
            )
            impact_row = decisions.get(parent_sec["section_id"]) if parent_sec else None
            decision = (
                impact_row.decision if impact_row else ImpactDecision.FULL_REWRITE
            )
            if parent_sec is not None and parent_sec.get("outline_node_id"):
                parent_chapter_id = f"CH-{parent_sec['outline_node_id']}"
                if self.chapters.chapter_has_locked_paragraph(parent_chapter_id):
                    decision = ImpactDecision.KEEP
            if parent_sec is None:
                decision = ImpactDecision.ADD_SECTION

            if decision in rewrite_decisions or parent_sec is None:
                section, report_memory = self._produce_section(
                    project_id=project_id,
                    edition_id=edition["edition_id"],
                    node=node,
                    source_ids=all_source_ids,
                    plan=plan,
                    chapter_units=chapter_units,
                    report_memory=report_memory,
                    prev_summary=prev_summary,
                    next_title=next_node.get("title") if next_node else None,
                    next_objective=next_node.get("objective") if next_node else None,
                    format_notes=format_notes,
                    chapter=chapter_by_node.get(node["node_id"]),
                    node_order=i + 1,
                )
                rewritten += 1
                action = decision.value
            elif decision in light_decisions:
                section = self._inherit_section(
                    project_id=project_id,
                    edition_id=edition["edition_id"],
                    node=node,
                    parent_section=parent_sec,
                    source_ids=all_source_ids,
                    scrub=(decision != ImpactDecision.KEEP),
                )
                if decision == ImpactDecision.KEEP:
                    section = self._scrub_existing(
                        project_id=project_id,
                        section=section,
                        source_ids=all_source_ids,
                    )
                report_memory = self._memory_from_skipped_section(
                    report_memory, section, node
                )
                kept += 1
                action = decision.value
            else:
                section, report_memory = self._produce_section(
                    project_id=project_id,
                    edition_id=edition["edition_id"],
                    node=node,
                    source_ids=all_source_ids,
                    plan=plan,
                    chapter_units=chapter_units,
                    report_memory=report_memory,
                    prev_summary=prev_summary,
                    next_title=next_node.get("title") if next_node else None,
                    next_objective=next_node.get("objective") if next_node else None,
                    format_notes=format_notes,
                    chapter=chapter_by_node.get(node["node_id"]),
                    node_order=i + 1,
                )
                rewritten += 1
                action = decision.value

            produced.append(
                {
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "status": section["status"],
                    "impact": action,
                    "parent_section_id": parent_sec["section_id"] if parent_sec else None,
                    "reasons": impact_row.reasons if impact_row else ["new section"],
                }
            )
            prev_summary = (section.get("content_markdown") or "")[:400]

        self.editions.update_status(edition["edition_id"], "IN_REVIEW")
        self.projects.update_stage(project_id, ProjectStage.REVIEWING.value)

        return {
            "edition_id": edition["edition_id"],
            "edition_number": edition["edition_number"],
            "snapshot_id": snapshot_id,
            "parent_edition_id": parent_edition_id,
            "new_source_ids": new_source_ids,
            "sections": produced,
            "rewritten_count": rewritten,
            "kept_count": kept,
            "impact": [
                {
                    "section_id": i.section_id,
                    "decision": i.decision.value,
                    "reasons": i.reasons,
                    "affected_claim_ids": i.affected_claim_ids,
                }
                for i in impact.section_impacts
            ],
            "stage": ProjectStage.REVIEWING.value,
            "mode": "incremental",
        }

    def _inherit_section(
        self,
        *,
        project_id: str,
        edition_id: str,
        node: dict,
        parent_section: dict,
        source_ids: list[str],
        scrub: bool,
    ) -> dict:
        section_id = f"SEC-{uuid.uuid4().hex[:10].upper()}"
        markdown = parent_section.get("content_markdown") or ""
        pack = self.evidence_packs.build_for_chapter(
            project_id=project_id,
            section_id=section_id,
            title=node["title"],
            objective=node.get("objective") or parent_section.get("objective") or "",
            chapter=None,
            research_questions=list(node.get("analysis_questions") or []),
            required_evidence_types=list(node.get("required_evidence_types") or []),
            source_ids=source_ids,
            previous_section_content=markdown if scrub else None,
        )
        if scrub or True:
            markdown = scrub_inherited_section(
                markdown, pack=pack, section_id=section_id
            )

        self.sections.create(
            {
                "section_id": section_id,
                "edition_id": edition_id,
                "outline_node_id": node["node_id"],
                "title": node["title"],
                "objective": node.get("objective") or parent_section.get("objective") or "",
                "status": "INHERITED",
                "content_markdown": markdown,
            }
        )
        pack_id = self.packs.save(section_id, pack.model_dump(mode="json"))
        for item in list(pack.definitions) + list(pack.supporting_facts):
            self.claims.save_evidence_item(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "page": item.page,
                    "evidence_type": item.type.value,
                    "statement": item.statement,
                    "block_ids": item.block_ids,
                    "confidence": item.confidence,
                }
            )
        for m in pack.metrics:
            self.claims.save_evidence_item(
                {
                    "evidence_id": m.metric_id,
                    "source_id": m.source_id,
                    "page": m.page_number,
                    "evidence_type": "METRIC",
                    "statement": f"{m.name} {m.change_value}{m.change_unit or ''}",
                    "block_ids": [],
                    "confidence": m.confidence,
                    "payload": m.model_dump(mode="json"),
                }
            )
        self.claims.delete_for_section(section_id)
        for claim, eids in extract_claims(
            edition_id=edition_id,
            section_id=section_id,
            markdown=markdown,
            pack=pack,
        ):
            self.claims.save_claim(claim.model_dump(), eids)
        self.sections.save_version(section_id, 1, markdown, "inherited from parent")
        return self.sections.update(
            section_id,
            content_markdown=markdown,
            status="DRAFT",
            revision_count=1,
            evidence_pack_id=pack_id,
        )

    def _scrub_existing(
        self,
        *,
        project_id: str,
        section: dict,
        source_ids: list[str],
    ) -> dict:
        pack_row = self.packs.get(section["evidence_pack_id"]) if section.get("evidence_pack_id") else None
        if not pack_row:
            return section
        pack = EvidencePack.model_validate(pack_row["pack"])
        md = scrub_inherited_section(
            section.get("content_markdown") or "",
            pack=pack,
            section_id=section["section_id"],
        )
        self.claims.delete_for_section(section["section_id"])
        for claim, eids in extract_claims(
            edition_id=section["edition_id"],
            section_id=section["section_id"],
            markdown=md,
            pack=pack,
        ):
            self.claims.save_claim(claim.model_dump(), eids)
        return self.sections.update(section["section_id"], content_markdown=md)

    def produce_section(
        self,
        project_id: str,
        edition_id: str,
        section_id: str,
    ) -> dict:
        section = self.sections.get(section_id)
        if not section or section["edition_id"] != edition_id:
            raise KeyError(section_id)
        source_ids = [
            s["source_id"]
            for s in self.sources.list_for_project(project_id)
            if s.get("role") == "EVIDENCE_SOURCE" and s.get("status") == "READY"
        ]
        node = {
            "node_id": section["outline_node_id"],
            "title": section["title"],
            "objective": section["objective"],
            "analysis_questions": [],
            "required_evidence_types": [],
            "level": 1,
        }
        plan = self.plans.latest_plan(project_id)
        outline = self.plans.get_outline(project_id)
        nodes = (outline or {}).get("nodes") or []
        chapter_units = self.blueprints.build_from_outline(outline_nodes=nodes)
        chapter_by_node = {c.node_id: c for c in chapter_units}
        if outline:
            match = next(
                (n for n in nodes if n["node_id"] == section["outline_node_id"]),
                None,
            )
            if match:
                node = match
        section_row, _ = self._produce_section(
            project_id=project_id,
            edition_id=edition_id,
            node=node,
            source_ids=source_ids,
            plan=plan,
            chapter_units=chapter_units,
            report_memory=ReportMemory(),
            existing_section_id=section_id,
            format_notes=_role_text_digest(
                self.conn, project_id, SourceRole.FORMAT_REFERENCE.value
            )
            or None,
            chapter=chapter_by_node.get(node.get("node_id")),
        )
        return section_row

    def _produce_section(
        self,
        *,
        project_id: str,
        edition_id: str,
        node: dict,
        source_ids: list[str],
        plan: dict | None = None,
        chapter_units: list | None = None,
        report_memory: ReportMemory | None = None,
        prev_summary: str | None = None,
        next_title: str | None = None,
        next_objective: str | None = None,
        existing_section_id: str | None = None,
        format_notes: str | None = None,
        chapter=None,
        node_order: int = 0,
    ) -> tuple[dict, ReportMemory]:
        memory = report_memory or ReportMemory()
        units = chapter_units if chapter_units is not None else (
            [chapter] if chapter is not None else []
        )
        section_id = existing_section_id or f"SEC-{uuid.uuid4().hex[:10].upper()}"
        if not existing_section_id:
            self.sections.create(
                {
                    "section_id": section_id,
                    "edition_id": edition_id,
                    "outline_node_id": node["node_id"],
                    "title": node["title"],
                    "objective": node.get("objective") or "",
                    "status": "RESEARCHING",
                }
            )
        else:
            self.sections.update(section_id, status="RESEARCHING")

        pack = self.evidence_packs.build_for_chapter(
            project_id=project_id,
            section_id=section_id,
            title=node["title"],
            objective=node.get("objective") or "",
            chapter=chapter,
            research_questions=list(node.get("analysis_questions") or []),
            required_evidence_types=list(node.get("required_evidence_types") or []),
            source_ids=source_ids,
        )
        pack_id = self.packs.save(section_id, pack.model_dump(mode="json"))
        self.sections.update(section_id, evidence_pack_id=pack_id, status="WRITING")

        for item in list(pack.definitions) + list(pack.supporting_facts):
            self.claims.save_evidence_item(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "page": item.page,
                    "evidence_type": item.type.value,
                    "statement": item.statement,
                    "block_ids": item.block_ids,
                    "confidence": item.confidence,
                }
            )
        for m in pack.metrics:
            self.claims.save_evidence_item(
                {
                    "evidence_id": m.metric_id,
                    "source_id": m.source_id,
                    "page": m.page_number,
                    "evidence_type": "METRIC",
                    "statement": f"{m.name} {m.change_value}{m.change_unit or ''}",
                    "block_ids": [],
                    "confidence": m.confidence,
                    "payload": m.model_dump(mode="json"),
                }
            )

        writing_ctx = self.blueprints.build_writing_context(
            plan=plan,
            chapter_units=units,
            node=node,
            chapter=chapter,
            pack=pack,
            report_memory=memory,
            prev_summary=prev_summary,
            next_title=next_title,
            next_objective=next_objective,
            format_notes=format_notes,
        )
        level = int(node.get("level") or 1)
        draft = self.writer.run(writing_ctx)
        markdown = render_chapter_markdown(draft, heading_level=level + 1)

        draft_validation = validate_draft(
            section_id=section_id,
            markdown=markdown,
            pack=pack,
            draft=draft,
            target_words=writing_ctx.target_words,
        )
        if not (markdown or "").strip():
            raise ValueError(
                f"ChapterWriter produced empty draft for {section_id}: "
                f"{[i.issue_type for i in draft_validation.issues]}"
            )

        self.chapters.save_chapter_draft(
            edition_id=edition_id,
            section_id=section_id,
            order_index=node_order,
            chapter_key=node.get("node_id") or section_id,
            draft=draft,
            body_markdown=markdown,
            summary="initial draft",
        )

        self.claims.delete_for_section(section_id)
        for claim, eids in extract_claims(
            edition_id=edition_id,
            section_id=section_id,
            markdown=markdown,
            pack=pack,
        ):
            self.claims.save_claim(claim.model_dump(), eids)

        self.sections.save_version(section_id, 1, markdown, "initial draft")
        section_row = self.sections.update(
            section_id,
            content_markdown=markdown,
            status="DRAFT",
            revision_count=1,
            evidence_pack_id=pack_id,
        )
        memory = self.blueprints.extend_report_memory(
            memory, draft=draft, summary=markdown[:400]
        )
        return section_row, memory
