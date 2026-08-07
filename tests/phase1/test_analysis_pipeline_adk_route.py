"""Phase 1: AnalysisPipeline uses one Canonical CorpusAnalyst path."""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.report_plan import CorpusAnalysis
from backend.orchestration.analysis_pipeline import AnalysisPipeline
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


def _sample_analysis() -> CorpusAnalysis:
    return CorpusAnalysis.model_validate(
        {
            "main_topic": "가공철근 MES",
            "technical_domain": "제조",
            "document_purpose": "분석",
            "key_entities": [],
            "key_technologies": [],
            "business_or_technical_problems": [],
            "system_components": [],
            "processes": [],
            "quantitative_findings": [],
            "qualitative_findings": [],
            "evidence_gaps": [],
            "contradictions": [],
            "recommended_report_focus": [],
            "previous_edition_analysis": None,
        }
    )


@pytest.mark.parametrize("mode", ["adk", "llm", "offline"])
def test_analysis_pipeline_modes_share_corpus_analyst(monkeypatch, tmp_path, mode):
    db = tmp_path / f"corpus-{mode}.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    try:
        _seed_ready_project(conn, project_id=f"PRJ-{mode.upper()}")
        called: dict[str, object] = {"agent": 0, "adk_runner": 0}

        def _fake_agent_run(self, context):
            called["agent"] = int(called["agent"]) + 1
            called["agent_mode"] = self.llm_mode
            return _sample_analysis()

        def _forbid_adk_run(self, config):
            called["adk_runner"] = int(called["adk_runner"]) + 1
            raise AssertionError("AdkRunner must not own corpus analysis after Phase 1")

        monkeypatch.setattr(
            "backend.agents.corpus_analyst.agent.CorpusAnalystAgent.run",
            _fake_agent_run,
        )
        monkeypatch.setattr("backend.adk_app.runner.AdkRunner.run", _forbid_adk_run)

        pipeline = AnalysisPipeline(conn, llm_mode=mode)
        # Pipeline must not construct AdkRunner for Source Intelligence.
        assert not hasattr(pipeline, "adk_runner")
        result = pipeline.run(f"PRJ-{mode.upper()}")
    finally:
        conn.close()

    assert called["agent"] == 1
    assert called["adk_runner"] == 0
    assert called["agent_mode"] == mode
    assert result["main_topic"] == "가공철근 MES"
    assert result["technical_domain"] == "제조"
    assert result["analysis"]["main_topic"] == "가공철근 MES"


def test_adk_mode_does_not_import_removed_corpus_workflow():
    """Removed Phase-1 dual-path modules must stay gone."""
    with pytest.raises(ModuleNotFoundError):
        __import__("backend.adk_app.workflows.planning_workflow")
    with pytest.raises(ModuleNotFoundError):
        __import__("backend.adk_app.agents.corpus_analyst")
    with pytest.raises(ModuleNotFoundError):
        __import__("backend.adk_app.prompt_loader")
