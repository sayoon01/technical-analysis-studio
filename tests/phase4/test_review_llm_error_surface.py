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


def test_normalize_editorial_issues_from_strings_and_partial_objects():
    raw = {
        "decision": "REVISE",
        "section_id": "SEC-9F07F8487B",
        "issues": [
            "The document repeats the goal statement twice.",
            {
                "issue_type": "REPETITION",
                "description": "Near-duplicate paragraphs.",
                "status": "OPEN",
            },
            {
                "issue_id": "ISSUE-002",
                "severity": "high",
                "problem": "Weak analysis section",
                "required_change": "Add concrete technical interpretation.",
            },
            {
                "issue_id": "      // No id",
                "description": "Garbage id from truncated model output",
                "recommendation": "Rewrite cleanly.",
                "severity": "INFO",
            },
        ],
        "duplicate_paragraph_ratio": 0.2,
        "promotional_phrase_count": 0,
        "terminology_inconsistency_count": 0,
        "critical_issue_count": 1,
    }
    fixed = _normalize_structured_raw("EditorialReview", raw)
    obj = EditorialReview.model_validate(fixed)
    assert len(obj.issues) == 4
    assert obj.issues[0].description.startswith("The document repeats")
    assert obj.issues[0].reviewer_type == "editorial"
    assert obj.issues[0].section_id == "SEC-9F07F8487B"
    assert obj.issues[0].issue_id.startswith("ISS-")
    assert obj.issues[0].severity.value == "MAJOR"
    assert obj.issues[1].issue_type == "REPETITION"
    assert "Address" in obj.issues[1].recommendation
    assert obj.issues[2].severity.value == "MAJOR"  # high → MAJOR
    assert "concrete technical" in obj.issues[2].recommendation
    assert obj.issues[3].issue_id.startswith("ISS-")
    assert "//" not in obj.issues[3].issue_id
    assert obj.issues[3].severity.value == "MINOR"  # INFO → MINOR


def test_normalize_technical_issues_string_list():
    raw = {
        "decision": "REVISE",
        "issues": ["Unsupported numeric claim without evidence."],
        "evidence_coverage": 0.5,
        "unsupported_claim_count": 1,
        "citation_mismatch_count": 0,
        "numeric_mismatch_count": 0,
        "critical_issue_count": 0,
    }
    fixed = _normalize_structured_raw("TechnicalReview", raw)
    obj = TechnicalReview.model_validate(fixed)
    assert len(obj.issues) == 1
    assert obj.issues[0].reviewer_type == "technical"
    assert obj.issues[0].section_id == "UNKNOWN"


def test_normalize_revision_result_changes_from_string_list():
    from backend.domain.review import RevisionResult

    raw = {
        "revision": "2",
        "updated_content": "Revised chapter body with citations intact.\n",
        "changes": [
            "- Fixed citation mismatch between claim and pack.",
            "- Clarified Wireless API terminology.",
        ],
        "resolved_issue_ids": ["ISS-1", {"issue_id": "ISS-2"}],
        "provenance": {"noise": True},
    }
    fixed = _normalize_structured_raw("RevisionResult", raw)
    assert "provenance" not in fixed
    assert fixed["revision"] == 2
    assert all(isinstance(c, dict) for c in fixed["changes"])
    assert fixed["changes"][0]["reason"].startswith("Fixed citation")
    assert fixed["changes"][0]["change_type"] == "NOTE"
    assert fixed["resolved_issue_ids"] == ["ISS-1", "ISS-2"]
    obj = RevisionResult.model_validate(fixed)
    assert len(obj.changes) == 2
    assert obj.updated_content.startswith("Revised")


def test_normalize_revision_result_revision_is_workflow_owned():
    from backend.domain.review import RevisionResult

    raw = {
        "revision": "2",
        "updated_content": "Revised body\n",
        "changes": ["- Fixed citation mismatch"],
        "resolved_issue_ids": [],
    }
    fixed = _normalize_structured_raw(
        "RevisionResult",
        raw,
        normalize_context={"expected_revision": 3},
    )
    obj = RevisionResult.model_validate(fixed)
    assert obj.revision == 3


def test_normalize_revision_result_wrong_revision_overridden_by_expected():
    from backend.domain.review import RevisionResult

    raw = {
        "revision": 999,
        "updated_content": "Revised body\n",
        "changes": ["- Fixed citation mismatch"],
        "resolved_issue_ids": [],
    }
    fixed = _normalize_structured_raw(
        "RevisionResult",
        raw,
        normalize_context={"expected_revision": 2},
    )
    obj = RevisionResult.model_validate(fixed)
    assert obj.revision == 2


def test_normalize_revision_result_unwrap_and_content_alias():
    from backend.domain.review import RevisionResult

    raw = {
        "revision_result": {
            "revision": 1,
            "markdown": "Body from alias field.",
            "changes": [{"change_type": "STRIP", "reason": "markers"}],
            "resolved_issue_ids": [],
        }
    }
    # unwrap happens in generate_structured; normalize expects inner dict
    inner = raw["revision_result"]
    fixed = _normalize_structured_raw("RevisionResult", inner)
    obj = RevisionResult.model_validate(fixed)
    assert obj.updated_content == "Body from alias field."


def test_normalize_revision_result_missing_content_still_fails():
    from pydantic import ValidationError

    from backend.domain.review import RevisionResult

    raw = {
        "revision": 1,
        "changes": ["only a note"],
        "resolved_issue_ids": [],
    }
    fixed = _normalize_structured_raw("RevisionResult", raw)
    with pytest.raises(ValidationError):
        RevisionResult.model_validate(fixed)


def test_normalize_revision_result_empty_content_fails():
    from pydantic import ValidationError

    from backend.domain.review import RevisionResult

    raw = {
        "revision": 1,
        "updated_content": "   ",
        "changes": ["only a note"],
        "resolved_issue_ids": [],
    }
    fixed = _normalize_structured_raw("RevisionResult", raw)
    with pytest.raises(ValidationError):
        RevisionResult.model_validate(fixed)


def test_normalize_revision_result_content_aliases_body_and_revised_markdown():
    from backend.domain.review import RevisionResult

    raw_body = {
        "revision": 1,
        "body": "Body alias text",
        "changes": ["- c1"],
        "resolved_issue_ids": None,
    }
    fixed_body = _normalize_structured_raw("RevisionResult", raw_body)
    obj_body = RevisionResult.model_validate(fixed_body)
    assert obj_body.updated_content == "Body alias text"

    raw_rm = {
        "revision": 1,
        "revised_markdown": "RM alias text",
        "changes": ["- c1"],
        "resolved_issue_ids": "ISS-1",
        "provenance": 1234,
    }
    fixed_rm = _normalize_structured_raw("RevisionResult", raw_rm)
    obj_rm = RevisionResult.model_validate(fixed_rm)
    assert obj_rm.updated_content == "RM alias text"
    assert obj_rm.resolved_issue_ids == ["ISS-1"]
    assert obj_rm.provenance == "online"


def test_safe_review_error_stage_specific():
    from backend.services.review_service import _safe_review_error

    exc = LlmError(
        "Structured generation failed after retries: "
        "changes.0 Input should be a valid dictionary"
    )
    assert (
        _safe_review_error(exc, failed_step="revising")
        == "Revision model output validation failed"
    )
    assert (
        _safe_review_error(exc, failed_step="technical_review")
        == "Technical review model output validation failed"
    )
    assert (
        _safe_review_error(exc, failed_step="editorial_review")
        == "Editorial review model output validation failed"
    )
    # Unknown step: generic validation (not the old technical/editorial blob)
    msg = _safe_review_error(exc, failed_step="starting")
    assert msg == "Review model output validation failed"
    assert "Technical/editorial" not in msg


def test_normalize_revision_result_missing_revision_uses_context():
    from backend.domain.review import RevisionResult

    raw = {
        "updated_content": "Revised body.\n",
        "changes": ["- Fixed citation mismatch"],
        "resolved_issue_ids": [],
    }
    fixed = _normalize_structured_raw(
        "RevisionResult",
        raw,
        normalize_context={"expected_revision": 2},
    )
    obj = RevisionResult.model_validate(fixed)
    assert obj.revision == 2
    assert obj.changes[0]["change_type"] == "NOTE"


def test_reviser_no_silent_fallback_and_malformed_changes_fail(monkeypatch):
    from backend.agents.reviser.agent import ReviserAgent
    from backend.domain.evidence import EvidencePack
    from backend.domain.review import EditorialReview, TechnicalReview
    from backend.domain.enums import ReviewDecision

    monkeypatch.setenv("TAS_LLM_MODE", "llm")
    from backend import config

    monkeypatch.setattr(
        config,
        "settings",
        config.Settings(llm_mode="llm", max_revisions=2),
    )

    def fake_generate(*_a, **_k):
        from backend.domain.review import RevisionResult

        return RevisionResult.model_validate(
            {
                "revision": 2,
                "updated_content": "본문\n",
                "changes": [{"change_type": "NOTE", "reason": ""}],
                "resolved_issue_ids": [],
            }
        )

    monkeypatch.setattr(
        "backend.agents.reviser.agent.generate_structured",
        fake_generate,
    )

    agent = ReviserAgent(llm_mode="llm")
    with pytest.raises(LlmError, match="malformed changes"):
        agent.run(
            title="Wireless API",
            objective="obj",
            markdown="draft",
            pack=EvidencePack(section_id="SEC-1", section_objective="o"),
            technical=TechnicalReview(decision=ReviewDecision.REVISE),
            editorial=EditorialReview(decision=ReviewDecision.PASS),
            revision=2,
        )


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


def test_save_technical_remints_colliding_issue_ids(tmp_path):
    """issue_id is a global PK — colliding LLM ids must not abort persistence."""
    db = tmp_path / "collide.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    reviews = ReviewRepository(conn)
    from backend.domain.enums import IssueSeverity, ReviewDecision
    from backend.domain.review import ReviewIssue, TechnicalReview

    first = TechnicalReview(
        decision=ReviewDecision.REVISE,
        issues=[
            ReviewIssue(
                issue_id="ISS-SAME",
                section_id="SEC-A",
                reviewer_type="technical",
                severity=IssueSeverity.MAJOR,
                issue_type="X",
                description="a",
                recommendation="fix",
            )
        ],
    )
    reviews.save_technical("SEC-A", first)
    reviews.supersede_open_issues("SEC-A")

    second = TechnicalReview(
        decision=ReviewDecision.REVISE,
        issues=[
            ReviewIssue(
                issue_id="ISS-SAME",  # collide with SUPERSEDED row
                section_id="SEC-B",
                reviewer_type="technical",
                severity=IssueSeverity.MINOR,
                issue_type="Y",
                description="b",
                recommendation="fix",
            )
        ],
    )
    rid = reviews.save_technical("SEC-B", second)
    assert rid.startswith("RV-")
    rows = list(
        conn.execute(
            "SELECT issue_id, section_id, status FROM review_issues WHERE section_id='SEC-B'"
        )
    )
    assert len(rows) == 1
    assert rows[0]["issue_id"] != "ISS-SAME"
    assert rows[0]["issue_id"].startswith("ISS-")
    assert rows[0]["status"] == "OPEN"


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
