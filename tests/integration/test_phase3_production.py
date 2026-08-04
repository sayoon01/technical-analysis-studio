"""Phase 3: evidence pack → writer → claim→page locations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.domain.enums import ProjectStage
from backend.services.edition_service import EditionService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.skills.analysis.section_writer import extract_citations
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "p3.db"
    data = tmp_path / "data"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("VECTOR_INDEX_DIR", str(data / "vector_indexes"))
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
        ),
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    return conn, store, tmp_path, data


def _ready_project(conn, store, tmp_path):
    pdf = build_sample_pdf(tmp_path / "mes.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn,
        llm_mode="offline",
        vector_root=Path(store.root).parent / "vector_indexes",
    )
    project = projects.create("phase3")
    uploaded = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(uploaded["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    return projects, plans, editions, project


def test_produce_sections_with_citations_and_claim_locations(env):
    conn, store, tmp_path, data = env
    projects, plans, editions, project = _ready_project(conn, store, tmp_path)

    result = editions.produce(project["project_id"])
    assert result["edition_id"]
    assert len(result["sections"]) >= 3
    assert result["stage"] in {
        ProjectStage.REVIEWING.value,
        ProjectStage.READY_FOR_EXPORT.value,
    }

    edition = editions.get_edition(result["edition_id"])
    assert edition["sections"]

    # Prefer a section that has inline [SRC-…, p.N] citations
    cited_section = None
    for s in edition["sections"]:
        full = editions.get_section(s["section_id"])
        if extract_citations(full.get("content_markdown") or ""):
            cited_section = full
            break

    assert cited_section is not None, "expected at least one section with citations"
    assert cited_section["evidence_pack"] is not None

    cites = extract_citations(cited_section["content_markdown"])
    assert cites, "markdown should contain [SRC-…, p.N] citations"

    # Claim → original page location (click-through)
    fact_claims = [
        c for c in cited_section["claims"] if c.get("verification_status") == "VERIFIED"
    ]
    assert fact_claims, "expected verified claims linked to evidence"
    loc = editions.resolve_claim_location(fact_claims[0]["claim_id"])
    assert loc["locations"], "claim must resolve to source page locations"
    loc0 = loc["locations"][0]
    assert loc0["page"] >= 1
    assert loc0["source_id"]
    assert loc0.get("image_path") or loc0.get("blocks")


def test_section_evidence_endpoint_shape(env):
    conn, store, tmp_path, data = env
    _, _, editions, project = _ready_project(conn, store, tmp_path)
    result = editions.produce(project["project_id"])
    section_id = result["sections"][0]["section_id"]
    ev = editions.get_section_evidence(section_id)
    assert ev["evidence_pack"]["section_id"] == section_id
    assert "supporting_facts" in ev["evidence_pack"] or "metrics" in ev["evidence_pack"]
