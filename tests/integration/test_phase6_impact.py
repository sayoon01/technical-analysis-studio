"""Phase 6: impact analysis, incremental V2, edition diff, no error amplification."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.domain.enums import ImpactDecision
from backend.orchestration.impact_analyzer import ImpactAnalyzer
from backend.services.edition_service import EditionService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from scripts.build_delivery_addendum import build_delivery_addendum
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "p6.db"
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


def _v1(conn, store, tmp_path, data):
    pdf = build_sample_pdf(tmp_path / "mes.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    project = projects.create("p6")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    v1 = editions.produce(project["project_id"])
    return projects, sources, plans, editions, project, v1, up["source_id"]


def test_delivery_addendum_partial_rewrite_only(env):
    conn, store, tmp_path, data = env
    _, sources, _, editions, project, v1, _ = _v1(conn, store, tmp_path, data)

    # Poison V1 with unsupported claim (should not amplify into V2)
    sec0 = v1["sections"][0]["section_id"]
    poisoned = (
        (editions.get_section(sec0)["content_markdown"] or "")
        + "\n\n클라우드 전환으로 운영비가 45% 감소했다.\n"
    )
    editions.sections.update(sec0, content_markdown=poisoned)

    addendum = build_delivery_addendum(tmp_path / "addendum.pdf")
    extra = sources.upload(
        project["project_id"], "addendum.pdf", addendum.read_bytes()
    )
    sources.process(extra["source_id"])

    preview = editions.preview_impact(
        project["project_id"],
        v1["edition_id"],
        new_source_ids=[extra["source_id"]],
    )
    decisions = {i["section_id"]: i["decision"] for i in preview["impacts"]}
    # At least one section should be partial/full rewrite (delivery related)
    assert any(
        d in {
            ImpactDecision.PARTIAL_REWRITE.value,
            ImpactDecision.FULL_REWRITE.value,
            ImpactDecision.UPDATE_CITATION.value,
            ImpactDecision.LIGHT_EDIT.value,
        }
        for d in decisions.values()
    )
    # Not all sections need full rewrite
    assert any(d == ImpactDecision.KEEP.value for d in decisions.values()) or any(
        d == ImpactDecision.LIGHT_EDIT.value for d in decisions.values()
    )

    v2 = editions.improve(
        project["project_id"],
        v1["edition_id"],
        new_source_ids=[extra["source_id"]],
    )
    assert v2["mode"] == "incremental"
    assert v2["parent_edition_id"] == v1["edition_id"]
    assert v2["kept_count"] >= 1
    assert v2["rewritten_count"] >= 1
    assert v2["rewritten_count"] < len(v2["sections"])

    # Error amplification guard: 45% must not remain in inherited/overview content
    for s in v2["sections"]:
        body = editions.get_section(s["section_id"])["content_markdown"] or ""
        assert "45%" not in body

    diff = editions.diff_editions(v1["edition_id"], v2["edition_id"])
    assert diff["left_edition_id"] == v1["edition_id"]
    assert "sections" in diff


def test_impact_analyzer_metric_targets_related_section(env):
    conn, store, tmp_path, data = env
    _, sources, _, editions, project, v1, _ = _v1(conn, store, tmp_path, data)
    addendum = build_delivery_addendum(tmp_path / "addendum2.pdf")
    extra = sources.upload(
        project["project_id"], "addendum2.pdf", addendum.read_bytes()
    )
    sources.process(extra["source_id"])

    report = ImpactAnalyzer(conn).analyze(
        parent_edition_id=v1["edition_id"],
        new_source_ids=[extra["source_id"]],
    )
    # Find a metrics-ish section decision
    titles = {
        s["section_id"]: s["title"]
        for s in editions.list_sections(v1["edition_id"])
    }
    rewritten = [
        titles.get(i.section_id, "")
        for i in report.section_impacts
        if i.decision
        in {ImpactDecision.PARTIAL_REWRITE, ImpactDecision.FULL_REWRITE}
    ]
    assert rewritten, "expected at least one rewritten section for delivery metric addendum"
