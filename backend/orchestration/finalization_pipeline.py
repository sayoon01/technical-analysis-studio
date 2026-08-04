"""Finalization + export pipeline."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.domain.enums import ProjectStage
from backend.services.publication_service import PublicationService
from backend.services.visual_service import VisualService
from backend.skills.export.docx_exporter import export_docx
from backend.skills.export.markdown_exporter import export_markdown
from backend.skills.export.pdf_exporter import export_pdf
from backend.skills.export.reference_builder import write_claim_ledger
from backend.skills.export.report_assembler import (
    markdown_to_html,
    number_figures,
    publication_to_markdown,
    write_json,
)
from backend.storage.edition_repository import (
    ClaimRepository,
    EditionRepository,
    SectionRepository,
)
from backend.storage.plan_repository import PlanRepository
from backend.storage.repositories import ProjectRepository, SourceRepository
from backend.storage.review_repository import ReviewRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinalizationPipeline:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.projects = ProjectRepository(conn)
        self.editions = EditionRepository(conn)
        self.sections = SectionRepository(conn)
        self.plans = PlanRepository(conn)
        self.sources = SourceRepository(conn)
        self.claims = ClaimRepository(conn)
        self.reviews = ReviewRepository(conn)
        self.visuals = VisualService(conn)
        self.publication = PublicationService()

    def run(self, edition_id: str) -> dict:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        project_id = edition["project_id"]
        self.projects.update_stage(project_id, ProjectStage.FINALIZING.value)
        self.editions.update_status(edition_id, "FINALIZING")

        plan = self.plans.latest_plan(project_id)
        title = (plan or {}).get("title") or f"Report {edition_id}"
        subtitle = (plan or {}).get("subtitle")
        sections = self.sections.list_for_edition(edition_id)

        out_root = (
            Path(settings.data_dir)
            / "exports"
            / project_id
            / f"edition-v{edition['edition_number']}"
        )
        if out_root.exists():
            shutil.rmtree(out_root)
        visuals_dir = out_root / "visuals"
        visuals_dir.mkdir(parents=True, exist_ok=True)

        requests = self.visuals.collect_requests(edition_id, project_id)
        visual_result = self.visuals.render_all(requests, visuals_dir)

        publication_doc = self.publication.build_document(
            title=title,
            subtitle=subtitle,
            sections=sections,
            visuals=visual_result,
        )
        md = publication_to_markdown(publication_doc)
        md = number_figures(md)
        html = markdown_to_html(md, title=title)

        report_md = export_markdown(out_root / "report.md", md)
        report_html = export_markdown(out_root / "report.html", html)
        report_docx = export_docx(
            out_root / "report.docx", md, title=title, image_root=visuals_dir
        )
        report_pdf = export_pdf(
            out_root / "report.pdf", md, title=title, image_root=visuals_dir
        )

        # Side cars
        all_claims = []
        review_summary = []
        for s in sections:
            all_claims.extend(self.claims.list_for_section(s["section_id"]))
            review_summary.append(
                {
                    "section_id": s["section_id"],
                    "title": s["title"],
                    "status": s.get("status"),
                    "reviews": self.reviews.list_for_section(s["section_id"])[:4],
                }
            )

        write_claim_ledger(out_root / "claim-evidence-ledger.xlsx", all_claims)
        write_json(
            out_root / "source-index.json",
            self.sources.list_for_project(project_id),
        )
        outline = self.plans.get_outline(project_id) or {}
        write_json(out_root / "outline.json", outline)
        write_json(out_root / "review-summary.json", review_summary)
        diff_payload: dict = {
            "edition_id": edition_id,
            "parent_edition_id": edition.get("parent_edition_id"),
        }
        if edition.get("parent_edition_id"):
            from backend.orchestration.edition_diff import EditionDiffer

            diff_payload = EditionDiffer(self.conn).diff(
                edition["parent_edition_id"], edition_id
            )
        write_json(out_root / "edition-diff.json", diff_payload)
        write_json(out_root / "visuals-index.json", visual_result["requests"])
        write_json(out_root / "publication-document.json", publication_doc.model_dump(mode="json"))
        self._save_publication_document(edition_id, publication_doc)

        zip_path = out_root.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in out_root.rglob("*"):
                if p.is_file():
                    zf.write(p, p.relative_to(out_root.parent))

        export_id = f"EXP-{uuid.uuid4().hex[:10].upper()}"
        self.conn.execute(
            """
            INSERT INTO exports (export_id, edition_id, format, storage_path, status, created_at)
            VALUES (?, ?, 'zip', ?, 'READY', ?)
            """,
            (export_id, edition_id, str(zip_path), _now()),
        )
        for fmt, p in (
            ("markdown", report_md),
            ("html", report_html),
            ("docx", report_docx),
            ("pdf", report_pdf),
        ):
            self.conn.execute(
                """
                INSERT INTO exports (export_id, edition_id, format, storage_path, status, created_at)
                VALUES (?, ?, ?, ?, 'READY', ?)
                """,
                (f"{export_id}-{fmt}", edition_id, fmt, str(p), _now()),
            )
        self.conn.commit()

        self.editions.update_status(edition_id, "EXPORTED")
        self.projects.update_stage(project_id, ProjectStage.EXPORTED.value)

        return {
            "export_id": export_id,
            "edition_id": edition_id,
            "bundle_dir": str(out_root),
            "zip_path": str(zip_path),
            "files": {
                "markdown": str(report_md),
                "html": str(report_html),
                "docx": str(report_docx),
                "pdf": str(report_pdf),
                "zip": str(zip_path),
            },
            "visuals": visual_result,
            "stage": ProjectStage.EXPORTED.value,
        }

    def _save_publication_document(self, edition_id: str, publication_doc) -> None:
        cols = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(publication_documents)").fetchall()
        }
        if not cols:
            return
        if {"publication_id", "edition_id", "title", "subtitle", "document_json", "created_at"}.issubset(cols):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO publication_documents (
                    publication_id, edition_id, title, subtitle, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"PUB-{uuid.uuid4().hex[:10].upper()}",
                    edition_id,
                    publication_doc.title,
                    publication_doc.subtitle,
                    json.dumps(publication_doc.model_dump(mode="json"), ensure_ascii=False),
                    _now(),
                ),
            )
            self.conn.commit()
