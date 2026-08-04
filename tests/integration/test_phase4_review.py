"""Phase 4: detect unsupported claims / numeric errors and revise."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.domain.enums import ProjectStage
from backend.domain.evidence import EvidencePack, EvidenceItem
from backend.domain.enums import EvidenceType
from backend.orchestration.quality_gate import can_finalize
from backend.services.edition_service import EditionService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.review_service import ReviewService
from backend.skills.analysis.review_offline import review_technical_offline
from backend.skills.analysis.revise_offline import revise_section_offline
from backend.domain.review import EditorialReview, ReviewDecision
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "p4.db"
    data = tmp_path / "data"
    monkeypatch.setenv("TAS_LLM_MODE", "offline")
    from backend import config

    monkeypatch.setattr(
        config,
        "settings",
        config.Settings(
            data_dir=data,
            database_url=f"sqlite:///{db}",
            vector_index_dir=data / "vector_indexes",
            llm_mode="offline",
            max_revisions=3,
        ),
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    return conn, store, tmp_path, data


def test_detect_unsupported_and_numeric_mismatch():
    pack = EvidencePack(
        section_id="SEC-TEST",
        section_objective="성과",
        supporting_facts=[
            EvidenceItem(
                evidence_id="EV-1",
                type=EvidenceType.METRIC,
                statement="시간당 생산량 8% 증가",
                source_id="SRC-1",
                page=16,
            )
        ],
        metrics=[],
    )
    bad_md = (
        "## 성과\n\n"
        "클라우드 전환으로 운영비가 45% 감소했다.\n\n"
        "시간당 생산량 8% 증가 [SRC-1, p.16]\n"
    )
    tech = review_technical_offline(
        section_id="SEC-TEST", markdown=bad_md, pack=pack, claims=[]
    )
    assert tech.numeric_mismatch_count >= 1
    assert tech.decision == ReviewDecision.REVISE
    assert not can_finalize(
        tech, EditorialReview(decision=ReviewDecision.PASS)
    )


def test_reviser_removes_bad_numeric():
    pack = EvidencePack(
        section_id="SEC-TEST",
        section_objective="성과",
        supporting_facts=[
            EvidenceItem(
                evidence_id="EV-1",
                type=EvidenceType.METRIC,
                statement="시간당 생산량 8% 증가",
                source_id="SRC-1",
                page=16,
            )
        ],
    )
    bad_md = "운영비가 45% 감소했다.\n\n시간당 생산량 8% 증가 [SRC-1, p.16]\n"
    tech = review_technical_offline(
        section_id="SEC-TEST", markdown=bad_md, pack=pack
    )
    editorial = EditorialReview(decision=ReviewDecision.PASS)
    revised = revise_section_offline(
        title="성과",
        objective="성과",
        markdown=bad_md,
        pack=pack,
        technical=tech,
        editorial=editorial,
        revision=2,
    )
    assert "45%" not in revised.updated_content
    tech2 = review_technical_offline(
        section_id="SEC-TEST",
        markdown=revised.updated_content,
        pack=pack,
    )
    assert tech2.numeric_mismatch_count == 0


def test_edition_review_loop_passes_clean_draft(env):
    conn, store, tmp_path, data = env
    pdf = build_sample_pdf(tmp_path / "mes.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    reviews = ReviewService(conn, llm_mode="offline")

    project = projects.create("p4")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"])

    # Inject a poisoned section to prove detection+fix path
    section_id = produced["sections"][0]["section_id"]
    section = editions.get_section(section_id)
    poisoned = (section["content_markdown"] or "") + "\n\n운영비가 45% 감소했다.\n"
    editions.sections.update(section_id, content_markdown=poisoned, status="DRAFT")

    # Single-section review should revise away 45%
    outcome = reviews.review_section(section_id)
    assert outcome["status"] in {"PASSED", "MANUAL_REVIEW"}
    fixed = editions.get_section(section_id)
    assert "45%" not in (fixed["content_markdown"] or "")

    # Full edition review
    result = reviews.review_edition(produced["edition_id"])
    assert "edition_id" in result
    assert "full_report" in result
    # After clean revision loop, prefer READY if all passed
    if result["all_passed"]:
        assert result["stage"] == ProjectStage.READY_FOR_EXPORT.value


def test_full_report_review_endpoint_records_result(env):
    conn, store, tmp_path, data = env
    pdf = build_sample_pdf(tmp_path / "mes-full.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    reviews = ReviewService(conn, llm_mode="offline")

    project = projects.create("p4-full")
    up = sources.upload(project["project_id"], "mes-full.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"])

    full = reviews.review_full_report(produced["edition_id"])
    assert full["edition_id"] == produced["edition_id"]
    assert full["status"] in {"PASSED", "REVISE"}
    rows = reviews.list_full_report_reviews(produced["edition_id"])
    assert rows
