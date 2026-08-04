from __future__ import annotations

import sqlite3

from backend.services.evidence_pack_service import EvidencePackService
from backend.services.report_blueprint_service import ReportBlueprintService
from backend.storage.database import init_schema


def test_report_blueprint_groups_top_level_nodes():
    svc = ReportBlueprintService()
    units = svc.build_from_outline(
        outline_nodes=[
            {
                "node_id": "N1",
                "parent_id": None,
                "level": 1,
                "order": 1,
                "title": "문제와 배경",
                "objective": "문제 분석",
                "analysis_questions": ["왜 필요한가?"],
                "planned_visuals": ["PROCESS_FLOW"],
            },
            {
                "node_id": "N1-1",
                "parent_id": "N1",
                "level": 2,
                "order": 2,
                "title": "기존 한계",
                "objective": "한계 정리",
            },
        ]
    )
    assert len(units) == 1
    assert units[0].node_id == "N1"
    assert units[0].subsection_node_ids == ["N1-1"]


def test_evidence_pack_service_builds_without_agent(tmp_path):
    db = tmp_path / "pack.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO projects (project_id, name, description, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("PRJ-1", "p", "", "ANALYZING", now, now),
    )
    conn.execute(
        """
        INSERT INTO sources (source_id, project_id, filename, mime_type, role, status, page_count, storage_path, ocr_quality, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("SRC-1", "PRJ-1", "a.pdf", "application/pdf", "EVIDENCE_SOURCE", "READY", 1, "x", 0.9, now),
    )
    conn.execute(
        """
        INSERT INTO content_blocks (
            block_id, source_id, page_number, block_type, text,
            bbox_x0, bbox_y0, bbox_x1, bbox_y1, reading_order, confidence, parent_section
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BLK-1", "SRC-1", 1, "TEXT", "시간당 생산량 8% 증가", 0, 0, 100, 20, 1, 0.9, ""),
    )
    conn.execute(
        """
        INSERT INTO metric_facts (
            metric_id, source_id, page_number, name, definition, measurement_method,
            baseline_value, result_value, change_value, change_unit, direction,
            confidence, verification_status, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("MET-1", "SRC-1", 1, "시간당 생산량", "", "", None, None, 8.0, "%", "INCREASE", 0.9, "VERIFIED", "{}"),
    )
    conn.commit()

    svc = EvidencePackService(conn)
    pack = svc.build_for_chapter(
        project_id="PRJ-1",
        section_id="SEC-1",
        title="정량 성과",
        objective="성과 요약",
        chapter=None,
        research_questions=["핵심 수치는?"],
        required_evidence_types=["METRIC"],
        source_ids=["SRC-1"],
    )
    conn.close()

    assert pack.section_id == "SEC-1"
    assert pack.metrics
