"""Phase 1 ingestion + retrieval integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.orchestration.source_pipeline import SourcePipeline
from backend.services.project_service import ProjectService, SourceService
from backend.skills.analysis.metric_extractor import extract_metrics_from_text
from backend.skills.ingestion.layout_analyzer import classify_page
from backend.skills.ingestion.pdf_parser import extract_pages
from backend.skills.retrieval.hybrid_search import hybrid_search
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    data = tmp_path / "data"
    vec = data / "vector_indexes"
    projects = data / "projects"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("VECTOR_INDEX_DIR", str(vec))

    # Reload settings
    from backend import config

    monkeypatch.setattr(
        config,
        "settings",
        config.Settings(
            data_dir=data,
            database_url=f"sqlite:///{db}",
            vector_index_dir=vec,
        ),
    )

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=projects)
    return conn, store, tmp_path


def test_pdf_page_order_and_text(tmp_env):
    conn, store, tmp_path = tmp_env
    pdf = build_sample_pdf(tmp_path / "sample.pdf")
    pages = extract_pages(pdf)
    assert len(pages) == 18
    assert pages[0].page_number == 1
    assert "MES" in pages[0].full_text
    assert "누락" in pages[11].full_text  # page 12
    assert pages[11].page_number == 12


def test_layout_classifies_diagram_pages(tmp_env):
    conn, store, tmp_path = tmp_env
    pdf = build_sample_pdf(tmp_path / "sample.pdf")
    pages = extract_pages(pdf)
    p13 = classify_page(pages[12])
    p14 = classify_page(pages[13])
    assert p13.page_type.value in {"DIAGRAM", "MIXED"}
    assert p14.page_type.value in {"DIAGRAM", "MIXED"}


def test_metric_extraction():
    text = (
        "시간당 생산량 8% 증가\n출하 클레임 60% 감소\n"
        "재공재고 33% 감소\n납기 준수율 24% 향상\n"
        "측정방법: 출하 예정일 이내 실제 출하량"
    )
    metrics = extract_metrics_from_text(text)
    names = " ".join(m.name for m in metrics)
    values = {m.change_value for m in metrics}
    assert 8.0 in values and 60.0 in values and 33.0 in values and 24.0 in values
    assert "생산" in names or "클레임" in names or "납기" in names


def test_process_pipeline_blocks_search_metrics(tmp_env):
    conn, store, tmp_path = tmp_env
    pdf = build_sample_pdf(tmp_path / "sample.pdf")

    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    project = projects.create("테스트 분석", "phase1")
    uploaded = sources.upload(project["project_id"], "sample.pdf", pdf.read_bytes())
    result = sources.process(uploaded["source_id"])

    assert result["status"] == "READY"
    assert result["page_count"] == 18
    assert result["block_count"] > 0
    assert result["chunk_count"] > 0

    page12 = sources.get_page(uploaded["source_id"], 12)
    assert "누락" in page12["text"] or any("누락" in b["text"] for b in page12["blocks"])
    assert page12["blocks"][0]["bbox"] is not None

    page13 = sources.get_page(uploaded["source_id"], 13)
    assert page13["page_type"] in {"DIAGRAM", "MIXED", "TEXT"}
    assert Path(page13["image_path"]).exists()

    page14 = sources.get_page(uploaded["source_id"], 14)
    assert "클라우드" in page14["text"] or "MES" in page14["text"]

    page16 = sources.get_page(uploaded["source_id"], 16)
    assert page16["metrics"], "expected metric facts on page 16"
    metric_values = {m["change_value"] for m in page16["metrics"]}
    assert 8.0 in metric_values or 60.0 in metric_values

    hits = hybrid_search(
        conn,
        project["project_id"],
        "납기 준수율",
        source_ids=[uploaded["source_id"]],
        vector_root=Path(store.root).parent / "vector_indexes",
    )
    # VectorStore uses settings.vector_index_dir — search via service
    hits2 = sources.search(project["project_id"], "클레임")
    assert hits2, "hybrid/keyword search should find 클레임"
