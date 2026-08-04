"""Phase 5: visuals + markdown/docx/pdf export bundle."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.services.edition_service import EditionService
from backend.services.export_service import ExportService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.review_service import ReviewService
from backend.services.visual_service import VisualService
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "p5.db"
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
        ),
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    return conn, store, tmp_path, data


def _produce(conn, store, tmp_path, data):
    pdf = build_sample_pdf(tmp_path / "mes.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    project = projects.create("p5")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"])
    # Export gate requires completed review
    reviews = ReviewService(conn, llm_mode="offline")
    reviews.review_edition(produced["edition_id"])
    return project, produced


def test_visuals_include_process_architecture_metrics(env):
    conn, store, tmp_path, data = env
    project, produced = _produce(conn, store, tmp_path, data)
    visuals = VisualService(conn)
    reqs = visuals.collect_requests(produced["edition_id"], project["project_id"])
    types = {r.visual_type.value for r in reqs}
    assert "PROCESS_FLOW" in types
    assert "ARCHITECTURE_DIAGRAM" in types
    assert "BAR_CHART" in types or "COMPARISON_TABLE" in types

    out = tmp_path / "visuals"
    result = visuals.render_all(reqs, out)
    assert result["unrendered"] == 0
    assert any(Path(p).suffix == ".png" for p in result["rendered"].values())
    assert any(Path(p).suffix == ".mmd" for p in result["rendered"].values())
    assert any(Path(p).suffix == ".dot" for p in result["rendered"].values())


def test_export_bundle_md_docx_pdf_zip(env):
    conn, store, tmp_path, data = env
    project, produced = _produce(conn, store, tmp_path, data)
    exports = ExportService(conn)
    result = exports.export_edition(produced["edition_id"])

    assert Path(result["files"]["markdown"]).is_file()
    assert Path(result["files"]["html"]).is_file()
    assert Path(result["files"]["docx"]).is_file()
    assert Path(result["files"]["pdf"]).is_file()
    assert Path(result["files"]["zip"]).is_file()

    md = Path(result["files"]["markdown"]).read_text(encoding="utf-8")
    assert "PROCESS" in md.upper() or "흐름" in md or "visuals/" in md or "그림" in md

    bundle = Path(result["bundle_dir"])
    assert (bundle / "claim-evidence-ledger.xlsx").is_file()
    assert (bundle / "outline.json").is_file()
    assert (bundle / "publication-document.json").is_file()
    assert (bundle / "visuals").is_dir()
    assert result["visuals"]["unrendered"] == 0


def test_export_gate_blocks_when_internal_marker_exists(env):
    conn, store, tmp_path, data = env
    _project, produced = _produce(conn, store, tmp_path, data)
    # Re-poison after review to ensure gate blocks export
    conn.execute(
        "UPDATE sections SET content_markdown = content_markdown || '\n<!-- VISUAL_REQUEST: BAR_CHART -->\n' WHERE section_id = ?",
        (produced["sections"][0]["section_id"],),
    )
    conn.commit()
    exports = ExportService(conn)
    readiness = exports.export_readiness(produced["edition_id"])
    assert not readiness["ready"]
    assert readiness["checks"]["internal_marker_sections"] >= 1
    with pytest.raises(ValueError):
        exports.export_edition(produced["edition_id"])
