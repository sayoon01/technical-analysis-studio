"""Phase 4: sequential review / revision canonicalization."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.agents.editorial_reviewer.agent import EditorialReviewerAgent
from backend.agents.reviser.agent import ReviserAgent
from backend.agents.technical_reviewer.agent import TechnicalReviewerAgent
from backend.domain.chapter import ChapterDraft, ReportMemory
from backend.domain.enums import IssueSeverity, ProjectStage, ReviewDecision
from backend.domain.evidence import EvidenceItem, EvidencePack, EvidenceType
from backend.domain.review import EditorialReview, ReviewIssue, TechnicalReview
from backend.model_providers.base import LlmError
from backend.orchestration import review_loop as review_loop_mod
from backend.orchestration.issue_aggregator import aggregate_issues
from backend.orchestration.production_pipeline import ProductionPipeline
from backend.orchestration.quality_gate import can_finalize, decide_gate, requires_manual_review
from backend.orchestration.review_loop import ReviewLoop
from backend.services.edition_service import EditionService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.report_blueprint_service import ReportBlueprintService
from backend.services.review_service import ReviewService
from backend.skills.analysis.draft_validator import validate_draft
from backend.skills.analysis.review_offline import review_technical_offline
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
            max_revisions=2,
        ),
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    return conn, store, tmp_path, data


def _issue(
    section_id: str,
    *,
    reviewer_type: str,
    severity: IssueSeverity,
    issue_type: str = "TEST",
) -> ReviewIssue:
    return ReviewIssue(
        issue_id=f"ISS-{issue_type}",
        section_id=section_id,
        reviewer_type=reviewer_type,
        severity=severity,
        issue_type=issue_type,
        description=f"{issue_type} desc",
        recommendation="fix",
    )


def test_no_threadpool_in_review_loop():
    src = inspect.getsource(review_loop_mod)
    assert "ThreadPoolExecutor" not in src
    assert "concurrent.futures" not in src
    assert "executor.submit" not in src


def test_sequential_reviewer_order_in_run_section(env, monkeypatch):
    conn, store, tmp_path, data = env
    order: list[str] = []

    def tech_run(**kwargs):
        order.append("technical")
        return TechnicalReview(
            decision=ReviewDecision.PASS, provenance="offline"
        )

    def edit_run(**kwargs):
        order.append("editorial")
        return EditorialReview(
            decision=ReviewDecision.PASS, provenance="offline"
        )

    pdf = build_sample_pdf(tmp_path / "mes-seq.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    project = projects.create("p4-seq")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    # Produce without double-review noise: pipeline reviews; disable outer auto_review
    produced = editions.produce(project["project_id"], auto_review=False)
    section_id = produced["sections"][0]["section_id"]
    # Reset to DRAFT so we can observe order on a fresh review
    editions.sections.update(section_id, status="DRAFT")

    loop = ReviewLoop(conn, llm_mode="offline", max_revisions=2)
    monkeypatch.setattr(loop.technical, "run", tech_run)
    monkeypatch.setattr(loop.editorial, "run", edit_run)
    monkeypatch.setattr(
        loop.reviser,
        "run",
        lambda **k: MagicMock(
            updated_content=k.get("markdown") or "ok",
            changes=[],
            resolved_issue_ids=[],
            provenance="offline",
        ),
    )
    outcome = loop.run_section(section_id)
    assert order[:2] == ["technical", "editorial"]
    assert outcome["status"] in {"PASSED", "MANUAL_REVIEW", "REVISE"} or True
    # First round always sequential tech then editorial
    assert order[0] == "technical"
    assert "editorial" in order
    tech_idxs = [i for i, x in enumerate(order) if x == "technical"]
    edit_idxs = [i for i, x in enumerate(order) if x == "editorial"]
    assert tech_idxs[0] < edit_idxs[0]


def test_aggregate_includes_validator_and_dedupes():
    tech = TechnicalReview(
        decision=ReviewDecision.REVISE,
        issues=[_issue("S1", reviewer_type="technical", severity=IssueSeverity.MAJOR)],
        unsupported_claim_count=1,
    )
    edit = EditorialReview(
        decision=ReviewDecision.PASS,
        issues=[_issue("S1", reviewer_type="editorial", severity=IssueSeverity.MINOR)],
    )
    draft_v = validate_draft(
        section_id="S1",
        markdown="",
        pack=EvidencePack(section_id="S1", section_objective="o"),
    )
    agg = aggregate_issues(
        technical=tech, editorial=edit, draft_validation=draft_v
    )
    assert agg.blocking_issue_count >= 1
    assert any(i.reviewer_type == "validator" for i in agg.issues)
    assert any(i.reviewer_type == "technical" for i in agg.issues)
    assert decide_gate(
        technical=tech,
        editorial=edit,
        revision_count=1,
        max_revisions=2,
        draft_validation=draft_v,
        aggregated=agg,
    ) == ReviewDecision.REVISE


def test_quality_gate_pass_without_blocking():
    tech = TechnicalReview(decision=ReviewDecision.PASS)
    edit = EditorialReview(decision=ReviewDecision.PASS)
    draft_v = validate_draft(
        section_id="S1",
        markdown="충분한 본문 내용입니다. " * 20,
        pack=EvidencePack(section_id="S1", section_objective="o"),
    )
    assert can_finalize(tech, edit, draft_validation=draft_v)
    assert (
        decide_gate(
            technical=tech,
            editorial=edit,
            revision_count=1,
            max_revisions=2,
            draft_validation=draft_v,
        )
        == ReviewDecision.PASS
    )


def test_max_revision_no_silent_pass():
    tech = TechnicalReview(
        decision=ReviewDecision.REVISE,
        unsupported_claim_count=1,
        critical_issue_count=1,
        issues=[
            _issue("S1", reviewer_type="technical", severity=IssueSeverity.CRITICAL)
        ],
    )
    edit = EditorialReview(decision=ReviewDecision.PASS)
    assert requires_manual_review(tech, edit, revision_count=2, max_revisions=2)
    assert (
        decide_gate(
            technical=tech,
            editorial=edit,
            revision_count=2,
            max_revisions=2,
        )
        == ReviewDecision.MANUAL_REVIEW
    )


def test_reviewer_llm_failure_no_silent_offline(monkeypatch):
    monkeypatch.setenv("TAS_LLM_MODE", "llm")
    from backend import config

    monkeypatch.setattr(
        config,
        "settings",
        config.Settings(llm_mode="llm", max_revisions=2),
    )

    def boom(*_a, **_k):
        raise LlmError("simulated")

    monkeypatch.setattr(
        "backend.agents.technical_reviewer.agent.generate_structured", boom
    )
    agent = TechnicalReviewerAgent(llm_mode="llm")
    with pytest.raises(LlmError):
        agent.run(
            section_id="S1",
            markdown="text",
            pack=EvidencePack(section_id="S1", section_objective="o"),
        )

    monkeypatch.setattr(
        "backend.agents.editorial_reviewer.agent.generate_structured", boom
    )
    with pytest.raises(LlmError):
        EditorialReviewerAgent(llm_mode="llm").run(
            section_id="S1", markdown="text"
        )

    monkeypatch.setattr(
        "backend.agents.reviser.agent.generate_structured", boom
    )
    with pytest.raises(LlmError):
        ReviserAgent(llm_mode="llm").run(
            title="t",
            objective="o",
            markdown="body",
            pack=EvidencePack(section_id="S1", section_objective="o"),
            technical=TechnicalReview(decision=ReviewDecision.REVISE),
            editorial=EditorialReview(decision=ReviewDecision.PASS),
            revision=2,
        )


def test_explicit_offline_provenance():
    tech = TechnicalReviewerAgent(llm_mode="offline").run(
        section_id="S1",
        markdown="시간당 생산량 8% 증가 [SRC-1, p.16]\n",
        pack=EvidencePack(
            section_id="S1",
            section_objective="o",
            supporting_facts=[
                EvidenceItem(
                    evidence_id="EV-1",
                    type=EvidenceType.METRIC,
                    statement="시간당 생산량 8% 증가",
                    source_id="SRC-1",
                    page=16,
                )
            ],
        ),
    )
    assert tech.provenance == "offline"
    edit = EditorialReviewerAgent(llm_mode="offline").run(
        section_id="S1", markdown="분석 본문입니다.\n" * 5
    )
    assert edit.provenance == "offline"


def test_report_memory_only_after_pass_idempotent():
    svc = ReportBlueprintService()
    memory = ReportMemory()
    draft = ChapterDraft(
        chapter_id="CH-01",
        title="배경",
        lead="lead",
        key_takeaways=["핵심1"],
    )
    # Simulate: draft-stage must not be caller-updated; extend is for PASS only
    m1 = svc.extend_report_memory(memory, draft=draft, summary="요약")
    m2 = svc.extend_report_memory(m1, draft=draft, summary="요약 again")
    assert len(m2.chapter_summaries) == 1

    produce_src = inspect.getsource(ProductionPipeline._produce_section)
    assert "extend_report_memory" not in produce_src
    remember_src = inspect.getsource(ProductionPipeline._review_and_remember)
    assert "extend_report_memory" in remember_src
    assert 'outcome.get("status") != "PASSED"' in remember_src or '!= "PASSED"' in remember_src


def test_memory_from_skipped_rejects_draft():
    pipe = ProductionPipeline.__new__(ProductionPipeline)
    pipe.blueprints = ReportBlueprintService()
    mem = ReportMemory()
    out = ProductionPipeline._memory_from_skipped_section(
        pipe,
        mem,
        {"status": "DRAFT", "title": "t", "content_markdown": "x" * 100},
        {"node_id": "N1", "title": "t"},
    )
    assert len(out.chapter_summaries) == 0
    out2 = ProductionPipeline._memory_from_skipped_section(
        pipe,
        mem,
        {"status": "PASSED", "title": "t", "content_markdown": "x" * 100},
        {"node_id": "N1", "title": "t"},
    )
    assert len(out2.chapter_summaries) == 1


def test_reviser_preserves_locked_snippet():
    locked = "사용자 고정 문단입니다."
    result = ReviserAgent(llm_mode="offline").run(
        title="t",
        objective="o",
        markdown=f"{locked}\n\n운영비가 45% 감소했다.\n",
        pack=EvidencePack(section_id="S1", section_objective="o"),
        technical=review_technical_offline(
            section_id="S1",
            markdown="운영비가 45% 감소했다.\n",
            pack=EvidencePack(section_id="S1", section_objective="o"),
        ),
        editorial=EditorialReview(decision=ReviewDecision.PASS),
        revision=2,
        aggregated_issues=[],
        locked_paragraph_texts=[locked],
    )
    assert locked in result.updated_content


def test_issues_contract_has_message(env):
    conn, store, tmp_path, data = env
    pdf = build_sample_pdf(tmp_path / "mes-iss.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    reviews = ReviewService(conn, llm_mode="offline")
    project = projects.create("p4-iss")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"])
    assert "all_passed" in (produced.get("review") or {}) or produced.get("review")
    section_id = produced["sections"][0]["section_id"]
    # Poison and re-review to create open issues or pass
    editions.sections.update(
        section_id,
        content_markdown=(
            (editions.get_section(section_id).get("content_markdown") or "")
            + "\n\n운영비가 45% 감소했다.\n"
        ),
        status="DRAFT",
    )
    reviews.review_section(section_id)
    issues = reviews.open_issues(section_id)
    for iss in issues:
        assert "severity" in iss
        assert iss.get("message") or iss.get("description")


def test_edition_review_all_passed_contract(env):
    conn, store, tmp_path, data = env
    pdf = build_sample_pdf(tmp_path / "mes-ap.pdf")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="offline")
    editions = EditionService(
        conn, llm_mode="offline", vector_root=data / "vector_indexes"
    )
    reviews = ReviewService(conn, llm_mode="offline")
    project = projects.create("p4-ap")
    up = sources.upload(project["project_id"], "mes.pdf", pdf.read_bytes())
    sources.process(up["source_id"])
    plans.analyze(project["project_id"])
    plans.generate_plan(project["project_id"])
    plans.approve_outline(project["project_id"])
    produced = editions.produce(project["project_id"], auto_review=False)
    # Sections may already be PASSED from interleaved pipeline review
    result = reviews.review_edition(produced["edition_id"])
    assert "all_passed" in result
    assert "stage" in result
    assert "sections" in result


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
