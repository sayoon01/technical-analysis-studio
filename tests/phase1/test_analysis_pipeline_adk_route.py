from __future__ import annotations

import sqlite3

from backend.orchestration.analysis_pipeline import AnalysisPipeline
from backend.storage.database import init_schema


def test_analysis_pipeline_routes_to_adk_runner(monkeypatch, tmp_path):
    db = tmp_path / "adk-route.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    try:
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO projects (project_id, name, description, stage, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("PRJ-ADK", "adk", "", "ANALYZING", now, now),
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
                "PRJ-ADK",
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

        called: dict[str, str] = {}

        def _fake_run(self, config):
            called["workflow"] = config.workflow_name
            return {
                "status": "COMPLETED",
                "output": {
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
                },
            }

        monkeypatch.setattr("backend.adk_app.runner.AdkRunner.run", _fake_run)
        pipeline = AnalysisPipeline(conn, llm_mode="adk")
        result = pipeline.run("PRJ-ADK")
    finally:
        conn.close()

    assert called["workflow"] == "planning_workflow.corpus_analysis"
    assert result["main_topic"] == "가공철근 MES"
    assert result["technical_domain"] == "제조"
