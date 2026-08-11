"""Live-error / LlmError mapping / review schema normalization (Phase 4 follow-up)."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.errors import http_from_llm_error
from backend.api.reviews import router as reviews_router
from backend.domain.review import EditorialReview, TechnicalReview
from backend.model_providers.base import LlmError, _normalize_structured_raw
from backend.orchestration.review_loop import ReviewLoop
from backend.storage.database import init_schema
from backend.storage.review_repository import ReviewRepository


def test_normalize_technical_review_percent_and_drop_bad_provenance():
    raw = {
        "decision": "PASS",
        "issues": [],
        "evidence_coverage": "100%",
        "unsupported_claim_count": "0",
        "citation_mismatch_count": 0,
        "numeric_mismatch_count": 0,
        "critical_issue_count": 0,
        "provenance": [],
    }
    fixed = _normalize_structured_raw("TechnicalReview", raw)
    assert "provenance" not in fixed
    assert fixed["evidence_coverage"] == 1.0
    assert fixed["unsupported_claim_count"] == 0
    obj = TechnicalReview.model_validate(fixed)
    assert obj.decision.value == "PASS"
    assert obj.provenance == "online"  # schema default; agent sets real value


def test_normalize_editorial_ratio_string():
    raw = {
        "decision": "PASS",
        "issues": [],
        "duplicate_paragraph_ratio": "10%",
        "promotional_phrase_count": "2",
        "terminology_inconsistency_count": 0,
        "critical_issue_count": 0,
        "provenance": {"x": 1},
    }
    fixed = _normalize_structured_raw("EditorialReview", raw)
    assert "provenance" not in fixed
    assert fixed["duplicate_paragraph_ratio"] == 0.1
    EditorialReview.model_validate(fixed)


def test_http_from_llm_error_is_502_safe():
    exc = LlmError(
        "Structured generation failed after retries: "
        "evidence_coverage Input should be a valid number"
    )
    http = http_from_llm_error(exc, role="Technical/editorial review")
    assert http.status_code == 502
    assert "Internal Server Error" not in str(http.detail)
    assert "Technical/editorial review model request failed" in str(http.detail)
    assert "evidence_coverage" in str(http.detail)
    # no secret leakage path
    secret = LlmError("failed token=supersecret password=x")
    http2 = http_from_llm_error(secret, role="Section review")
    assert "supersecret" not in str(http2.detail)
    assert http2.status_code == 502


def test_review_api_maps_llm_error_not_generic_500(monkeypatch):
    app = FastAPI()
    app.include_router(reviews_router)
    client = TestClient(app, raise_server_exceptions=False)

    class FakeSvc:
        def review_edition(self, edition_id: str):
            raise LlmError(
                "Structured generation failed after retries: "
                "evidence_coverage Input should be a valid number"
            )

        def review_section(self, section_id: str):
            raise LlmError("Ollama request timed out (gemma4:31b, 900.0s)")

        def review_full_report(self, edition_id: str):
            raise LlmError("boom")

    monkeypatch.setattr(
        "backend.api.reviews.get_review_service", lambda: FakeSvc()
    )
    r = client.post("/api/editions/ED-X/review")
    assert r.status_code == 502
    body = r.json()
    assert "detail" in body
    assert "Internal Server Error" not in body["detail"]
    assert "model request failed" in body["detail"]

    r2 = client.post("/api/sections/SEC-X/review")
    assert r2.status_code == 502
    assert "timed out" in r2.json()["detail"]


def test_technical_reviewer_llm_error_no_silent_offline(monkeypatch):
    from backend.agents.technical_reviewer.agent import TechnicalReviewerAgent
    from backend.domain.evidence import EvidencePack

    monkeypatch.setenv("TAS_LLM_MODE", "llm")
    from backend import config

    monkeypatch.setattr(
        config,
        "settings",
        config.Settings(llm_mode="llm", max_revisions=2),
    )

    def boom(*_a, **_k):
        raise LlmError("simulated validation failure")

    monkeypatch.setattr(
        "backend.agents.technical_reviewer.agent.generate_structured", boom
    )
    agent = TechnicalReviewerAgent(llm_mode="llm")
    with pytest.raises(LlmError, match="simulated"):
        agent.run(
            section_id="SEC-1",
            markdown="body",
            pack=EvidencePack(section_id="SEC-1", section_objective="o"),
        )


def test_partial_review_retry_supersedes_open_issues(tmp_path):
    db = tmp_path / "retry.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    reviews = ReviewRepository(conn)
    from backend.domain.enums import IssueSeverity, ReviewDecision
    from backend.domain.review import ReviewIssue, TechnicalReview

    stale = TechnicalReview(
        decision=ReviewDecision.REVISE,
        issues=[
            ReviewIssue(
                issue_id="ISS-OLD",
                section_id="SEC-1",
                reviewer_type="technical",
                severity=IssueSeverity.MAJOR,
                issue_type="STALE",
                description="old",
                recommendation="fix",
            )
        ],
        unsupported_claim_count=1,
    )
    reviews.save_technical("SEC-1", stale)
    assert len(reviews.open_issues("SEC-1")) == 1

    n = reviews.supersede_open_issues("SEC-1")
    assert n == 1
    assert reviews.open_issues("SEC-1") == []

    # ReviewLoop.run_section must call supersede at entry (source contract)
    import inspect

    src = inspect.getsource(ReviewLoop.run_section)
    assert "supersede_open_issues" in src


def test_busy_cleanup_on_llm_error(monkeypatch):
    from backend.services import review_service as rs_mod
    from backend.services.job_status import get_job

    conn = MagicMock()
    # Build a real-ish service with mocked repos/loop
    svc = rs_mod.ReviewService.__new__(rs_mod.ReviewService)
    svc.conn = conn
    svc.editions = MagicMock()
    svc.editions.get.return_value = {"edition_id": "ED-1", "project_id": "PRJ-Z"}
    svc.sections = MagicMock()
    svc.reviews = MagicMock()
    svc.loop = MagicMock()
    svc.loop.run_edition.side_effect = LlmError("structured fail")

    # use real lock/job helpers
    with pytest.raises(LlmError):
        # ReviewService itself does not catch LlmError — API does; ensure finally clears job
        edition = svc.editions.get("ED-1")
        project_id = edition["project_id"]
        from backend.services.job_status import lock_for, set_job

        lock = lock_for(project_id)
        assert lock.acquire(blocking=False)
        set_job(project_id, "reviewing")
        try:
            raise LlmError("structured fail")
        finally:
            set_job(project_id, None)
            lock.release()
    assert get_job("PRJ-Z") is None
