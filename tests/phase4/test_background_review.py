"""Phase 4.2: background edition review + progress + revision issue cleanup."""

from __future__ import annotations

import inspect
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from backend.api.reviews import router as reviews_router
from backend.domain.enums import IssueSeverity, ReviewDecision
from backend.domain.review import EditorialReview, ReviewIssue, TechnicalReview
from backend.model_providers.base import LlmError
from backend.orchestration.review_loop import ReviewLoop
from backend.services import job_status as js
from backend.services.edition_service import EditionService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.review_service import ReviewService
from backend.storage.database import init_schema
from backend.storage.file_store import FileStore
from backend.storage.review_repository import ReviewRepository
from scripts.build_sample_pdf import build_sample_pdf


@pytest.fixture()
def clean_jobs():
    js._jobs.clear()
    js._outcomes.clear()
    yield
    js._jobs.clear()
    js._outcomes.clear()


@pytest.fixture()
def env(tmp_path, monkeypatch, clean_jobs):
    db = tmp_path / "p42.db"
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
            max_revisions=2,
        ),
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    return conn, store, tmp_path, data


def _issue(section_id: str, issue_id: str) -> ReviewIssue:
    return ReviewIssue(
        issue_id=issue_id,
        section_id=section_id,
        reviewer_type="technical",
        severity=IssueSeverity.MAJOR,
        issue_type="TEST",
        description="problem",
        recommendation="fix",
    )


def _produce_edition(conn, store, tmp_path, data):
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    project = projects.create("p42")
    pdf = build_sample_pdf(tmp_path / "mes.pdf")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"], auto_review=False)
    return project, produced, editions


def test_job_status_progress_and_failure_outcome_additive(clean_jobs):
    js.set_job(
        "PRJ-1",
        "reviewing",
        current_step="technical_review",
        completed_sections=2,
        total_sections=10,
        current_section="SEC-A",
        current_section_title="Alpha",
    )
    job = js.get_job("PRJ-1")
    assert job is not None
    assert job["phase"] == "reviewing"
    assert job["current_step"] == "technical_review"
    assert "기술 검토" in job["label"]
    assert job["completed_sections"] == 2

    js.update_job("PRJ-1", current_step="editorial_review", completed_sections=3)
    assert js.get_job("PRJ-1")["current_step"] == "editorial_review"

    js.finish_job(
        "PRJ-1",
        error="Technical/editorial review model output validation failed",
        failed_step="editorial_review",
        failed_section="SEC-A",
    )
    assert js.get_job("PRJ-1") is None
    out = js.get_job_outcome("PRJ-1")
    assert out is not None
    assert out["error"]
    assert out["failed_step"] == "editorial_review"
    assert "traceback" not in out["error"].lower()


def test_revision_round_supersedes_open_issues_each_round(env, monkeypatch):
    conn, store, tmp_path, data = env
    _project, produced, editions = _produce_edition(conn, store, tmp_path, data)
    section_id = produced["sections"][0]["section_id"]
    editions.sections.update(section_id, status="DRAFT")
    section = editions.sections.get(section_id)

    calls = {"n": 0}

    class Tech:
        def run(self, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                return TechnicalReview(
                    decision=ReviewDecision.REVISE,
                    issues=[_issue(section_id, "ISS-R1")],
                    unsupported_claim_count=1,
                    critical_issue_count=1,
                    provenance="offline",
                )
            return TechnicalReview(
                decision=ReviewDecision.PASS,
                issues=[],
                provenance="offline",
            )

    class Edit:
        def run(self, **_k):
            return EditorialReview(
                decision=ReviewDecision.PASS, issues=[], provenance="offline"
            )

    class Rev:
        def run(self, **_k):
            from backend.domain.review import RevisionResult

            return RevisionResult(
                revision=2,
                updated_content=(section.get("content_markdown") or "x") + "\nrevised",
                changes=[{"op": "append"}],
                resolved_issue_ids=["ISS-R1"],
                provenance="offline",
            )

    loop = ReviewLoop(conn, llm_mode="offline", max_revisions=2)
    loop.technical = Tech()
    loop.editorial = Edit()
    loop.reviser = Rev()
    outcome = loop.run_section(section_id)
    assert outcome["status"] in {"PASSED", "MANUAL_REVIEW"}
    open_ids = {i["issue_id"] for i in ReviewRepository(conn).open_issues(section_id)}
    assert "ISS-R1" not in open_ids
    src = inspect.getsource(ReviewLoop.run_section)
    assert src.count("supersede_open_issues") >= 1


def test_background_start_returns_fast_and_uses_same_review_loop(env, monkeypatch):
    conn, store, tmp_path, data = env
    project, produced, _editions = _produce_edition(conn, store, tmp_path, data)
    edition_id = produced["edition_id"]
    pid = project["project_id"]

    seen_conns: list[int] = []
    real_connect = __import__("backend.storage.database", fromlist=["connect"]).connect

    def tracking_connect(*a, **k):
        c = real_connect(*a, **k)
        seen_conns.append(id(c))
        return c

    monkeypatch.setattr("backend.services.review_service.connect", tracking_connect)

    src = inspect.getsource(ReviewService.start_edition_review)
    assert "threading.Thread" in src
    assert "run_edition" in src

    svc = ReviewService(conn, llm_mode="offline")
    request_conn_id = id(conn)
    t0 = time.perf_counter()
    out = svc.start_edition_review(edition_id)
    assert time.perf_counter() - t0 < 2.0
    assert out["accepted"] is True
    assert out["phase"] == "reviewing"
    assert out["edition_id"] == edition_id

    deadline = time.time() + 90
    while time.time() < deadline:
        if js.get_job(pid) is None and not js.lock_for(pid).locked():
            break
        time.sleep(0.1)

    assert js.get_job(pid) is None
    assert not js.lock_for(pid).locked()
    outcome = js.get_job_outcome(pid)
    assert outcome is not None
    assert outcome.get("error") is None
    assert outcome.get("result", {}).get("edition_id") == edition_id
    assert request_conn_id not in seen_conns
    assert len(seen_conns) >= 1


def test_duplicate_background_start_rejected(env):
    conn, _store, _tmp, _data = env
    svc = ReviewService(conn, llm_mode="offline")
    svc.editions.get = MagicMock(  # type: ignore[method-assign]
        return_value={"edition_id": "ED-D", "project_id": "PRJ-D"}
    )
    svc.sections.list_for_edition = MagicMock(return_value=[])  # type: ignore[method-assign]

    lock = js.lock_for("PRJ-D")
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(ValueError, match="already running"):
            svc.start_edition_review("ED-D")
    finally:
        lock.release()


def test_background_failure_retains_error_and_releases_lock(clean_jobs, monkeypatch):
    conn = MagicMock()
    svc = ReviewService(conn, llm_mode="offline")
    svc.editions.get = MagicMock(  # type: ignore[method-assign]
        return_value={"edition_id": "ED-F", "project_id": "PRJ-F"}
    )
    svc.sections.list_for_edition = MagicMock(  # type: ignore[method-assign]
        return_value=[{"section_id": "SEC-1", "status": "DRAFT", "title": "T"}]
    )

    def boom_connect():
        raise LlmError("Structured generation failed after retries: validation")

    monkeypatch.setattr("backend.services.review_service.connect", boom_connect)
    out = svc.start_edition_review("ED-F")
    assert out["accepted"] is True
    deadline = time.time() + 5
    while time.time() < deadline and js.get_job("PRJ-F") is not None:
        time.sleep(0.05)
    assert js.get_job("PRJ-F") is None
    assert not js.lock_for("PRJ-F").locked()
    outcome = js.get_job_outcome("PRJ-F")
    assert outcome and outcome.get("error")
    assert "validation" in outcome["error"].lower() or "failed" in outcome["error"].lower()


def test_sync_review_route_still_present_and_start_is_additive():
    app = FastAPI()
    app.include_router(reviews_router)
    paths = app.openapi()["paths"]
    assert "/api/editions/{edition_id}/review" in paths
    assert "post" in paths["/api/editions/{edition_id}/review"]
    assert "/api/editions/{edition_id}/review/start" in paths
    assert "post" in paths["/api/editions/{edition_id}/review/start"]
    # Existing sync contract keeps all_passed semantics via ReviewService.review_edition
    assert "start_edition_review" in inspect.getsource(ReviewService)
    assert "review_edition" in inspect.getsource(ReviewService)


def test_status_includes_additive_progress_fields(env):
    conn, store, tmp_path, data = env
    project, _produced, _ed = _produce_edition(conn, store, tmp_path, data)
    pid = project["project_id"]
    plans = PlanService(conn, llm_mode="offline")
    js.set_job(
        pid,
        "reviewing",
        current_step="technical_review",
        completed_sections=1,
        total_sections=5,
        current_section="SEC-X",
        current_section_title="Title X",
    )
    try:
        st = plans.generation_status(pid)
        assert st["busy"] is True
        assert st["phase"] == "reviewing"
        assert st["completed_sections"] == 1
        assert st["total_sections"] == 5
        assert st["current_section"] == "SEC-X"
        assert st["current_step"] == "technical_review"
    finally:
        js.set_job(pid, None)


def test_review_loop_progress_callback_optional(env):
    conn, store, tmp_path, data = env
    _project, produced, _editions = _produce_edition(conn, store, tmp_path, data)
    events: list[dict] = []
    loop = ReviewLoop(
        conn, llm_mode="offline", max_revisions=1, on_progress=events.append
    )
    result = loop.run_edition(produced["edition_id"])
    assert "all_passed" in result
    assert any(e.get("current_step") == "starting" for e in events)
    assert any(e.get("total_sections") is not None for e in events)


def test_existing_sync_review_edition_still_blocks_and_returns(env, clean_jobs):
    conn, store, tmp_path, data = env
    project, produced, _editions = _produce_edition(conn, store, tmp_path, data)
    svc = ReviewService(conn, llm_mode="offline")
    result = svc.review_edition(produced["edition_id"])
    assert "all_passed" in result
    assert js.get_job(project["project_id"]) is None
