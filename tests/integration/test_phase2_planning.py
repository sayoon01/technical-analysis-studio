"""Phase 2: analysis + dynamic outline (domain-agnostic)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.domain.enums import ProjectStage
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_npu_pdf import build_npu_pdf
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "p2.db"
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
    return conn, store, tmp_path


def _ingest(conn, store, tmp_path, pdf_builder, name: str):
    pdf = pdf_builder(tmp_path / f"{name}.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    project = projects.create(name)
    uploaded = sources.upload(project["project_id"], f"{name}.pdf", pdf.read_bytes())
    sources.process(uploaded["source_id"])
    analysis = plans.analyze(project["project_id"])
    plan = plans.generate_plan(project["project_id"])
    return plans, project, analysis, plan


def test_mes_and_npu_produce_different_outlines(env):
    conn, store, tmp_path = env
    _, _, a1, p1 = _ingest(conn, store, tmp_path, build_sample_pdf, "mes")
    _, _, a2, p2 = _ingest(conn, store, tmp_path, build_npu_pdf, "npu")

    assert a1["main_topic"] != a2["main_topic"]
    assert p1["title"] != p2["title"]

    titles1 = {n["title"] for n in p1["plan"]["outline"]}
    titles2 = {n["title"] for n in p2["plan"]["outline"]}
    assert titles1 != titles2

    # MES corpus should surface manufacturing-ish signals; NPU thermal signals
    blob1 = " ".join(titles1) + a1["main_topic"]
    blob2 = " ".join(titles2) + a2["main_topic"]
    assert ("MES" in blob1) or ("생산" in blob1) or ("클레임" in blob1)
    assert ("NPU" in blob2) or ("열" in blob2) or ("GPU" in blob2)


def test_outline_edit_and_approve(env):
    conn, store, tmp_path = env
    plans, project, _, plan = _ingest(
        conn, store, tmp_path, build_sample_pdf, "mes2"
    )
    outline = plans.get_outline(project["project_id"])
    assert outline["approved"] is False
    assert ProjectStage(
        ProjectService(conn).get(project["project_id"])["stage"]
    ) == ProjectStage.WAITING_FOR_OUTLINE_APPROVAL

    nodes = outline["nodes"]
    nodes[0]["title"] = "분석 개요 (수정)"
    patched = plans.patch_outline(project["project_id"], nodes)
    assert patched["nodes"][0]["title"] == "분석 개요 (수정)"

    plans.patch_plan(project["project_id"], title="커스텀 제목")
    approved = plans.approve_outline(project["project_id"])
    assert approved["stage"] == ProjectStage.PRODUCING.value
    assert approved["approved"] is True


def test_plan_contains_title_candidates(env):
    conn, store, tmp_path = env
    _, _, _, plan = _ingest(conn, store, tmp_path, build_sample_pdf, "mes3")
    candidates = plan["plan"].get("title_candidates") or []
    assert len(candidates) >= 1
    assert candidates[0].get("title")


def test_no_hardcoded_mes_outline_when_npu(env):
    conn, store, tmp_path = env
    _, _, _, plan = _ingest(conn, store, tmp_path, build_npu_pdf, "npu2")
    titles = [n["title"] for n in plan["plan"]["outline"]]
    # Must not emit MES-specific canned chapters
    forbidden = {"D’MES 솔루션의 구성과 주요 기능", "가공철근 제조업무와 기존 시스템의 문제"}
    assert forbidden.isdisjoint(set(titles))
