"""Phase 1: Analyze uses persistent job + ADK worker path."""

from __future__ import annotations

import inspect
import sqlite3

import pytest
from google.genai import types
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.lite_llm import LiteLLMClient, LiteLlm
from google.adk.agents import LlmAgent

from backend.application.analyze_jobs import AnalyzeJobUseCase
from backend.jobs.job_worker import AnalyzeJobWorker
from backend.storage.database import init_schema


def _seed_ready_project(conn: sqlite3.Connection, project_id: str = "PRJ-ADK") -> None:
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO projects (project_id, name, description, stage, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, "adk", "", "ANALYZING", now, now),
    )
    conn.execute(
        """
        INSERT INTO sources (
            source_id, project_id, role, filename, mime_type, status,
            page_count, storage_path, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "SRC-1",
            project_id,
            "EVIDENCE_SOURCE",
            "a.pdf",
            "application/pdf",
            "READY",
            1,
            "data/projects/a.pdf",
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO source_pages (
            page_id, source_id, page_number, page_type, text_layer_available, image_path, width, height
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("PG-1", "SRC-1", 1, "TEXT", 1, "", 1000.0, 1400.0),
    )
    conn.execute(
        """
        INSERT INTO content_blocks (
            block_id, source_id, page_number, block_type, text,
            bbox_x0, bbox_y0, bbox_x1, bbox_y1, reading_order, confidence, parent_section
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BLK-1", "SRC-1", 1, "TEXT", "가공철근 MES 구축", 0, 0, 100, 30, 1, 0.99, ""),
    )
    conn.commit()


class FakeJsonLlm(BaseLlm):
    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        if "corpus" in self.model:
            out = (
                '{"main_topic":"가공철근 MES","technical_domain":"제조","document_purpose":"분석",'
                '"key_entities":[],"key_technologies":[],"business_or_technical_problems":[],'
                '"system_components":[],"processes":[],"qualitative_findings":[],'
                '"evidence_gaps":[],"contradictions":[],"recommended_report_focus":[]}'
            )
        else:
            out = (
                '{"decisions":[{"evidence_id":"EVD-BLK-1","status":"accepted","reason":"supported"}],'
                '"accepted_count":1,"rejected_count":0,"failed_count":0}'
            )
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=out)]),
            partial=False,
        )


def test_adk_signatures_match_phase1_constraints():
    assert "parent_context" in str(inspect.signature(LlmAgent.run_async))
    assert "timeout" in str(inspect.signature(LlmAgent))
    assert "llm_client" in str(inspect.signature(LiteLlm))
    assert "acompletion" in dir(LiteLLMClient)


def test_analyze_job_worker_runs_adk_vertical_slice(monkeypatch, tmp_path):
    db = tmp_path / "phase1-adk.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    _seed_ready_project(conn, project_id="PRJ-ADK")

    monkeypatch.setattr(
        "backend.adk_app.model_adapter.build_agent_model",
        lambda name: FakeJsonLlm(model=f"fake-{name}"),
    )
    monkeypatch.setattr(
        "backend.adk_app.agents.source_intelligence_agent.build_agent_model",
        lambda name: FakeJsonLlm(model=f"fake-{name}"),
    )
    monkeypatch.setattr(
        "backend.adk_app.agents.evidence_curator_agent.build_agent_model",
        lambda name: FakeJsonLlm(model=f"fake-{name}"),
    )
    started = AnalyzeJobUseCase(conn).start("PRJ-ADK")
    assert started["accepted"] is True
    assert started["busy"] is True
    assert started["job_id"]

    worker = AnalyzeJobWorker(conn)
    assert worker.run_once() is True

    job = conn.execute(
        "SELECT status, adk_invocation_id FROM jobs WHERE job_id = ?",
        (started["job_id"],),
    ).fetchone()
    assert job is not None
    assert job["status"] == "completed"
    assert job["adk_invocation_id"]

    ev_agents = {
        r["agent_name"]
        for r in conn.execute(
            "SELECT agent_name FROM job_events WHERE job_id = ?", (started["job_id"],)
        ).fetchall()
    }
    assert "SourceIntelligenceAgent" in ev_agents
    assert "EvidenceCuratorAgent" in ev_agents

    analysis = conn.execute(
        "SELECT payload_json FROM corpus_analyses WHERE project_id = ?",
        ("PRJ-ADK",),
    ).fetchone()
    assert analysis is not None
    assert "가공철근 MES" in analysis["payload_json"]


def test_concurrent_analyze_requests_are_db_guarded(tmp_path):
    db = tmp_path / "phase1-adk-concurrency.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    _seed_ready_project(conn, project_id="PRJ-CONC")
    usecase = AnalyzeJobUseCase(conn)
    first = usecase.start("PRJ-CONC")
    assert first["accepted"] is True
    with pytest.raises(ValueError, match="already running"):
        usecase.start("PRJ-CONC")
    count = conn.execute(
        "SELECT COUNT(*) c FROM jobs WHERE project_id = ? AND status IN ('queued','running')",
        ("PRJ-CONC",),
    ).fetchone()["c"]
    assert count == 1
