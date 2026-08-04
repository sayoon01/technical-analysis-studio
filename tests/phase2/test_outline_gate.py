from __future__ import annotations

from backend.domain.report_plan import OutlineNode, ReportPlan
from backend.skills.analysis.outline_quality_gate import validate_outline


def _node(i: int, title: str) -> OutlineNode:
    return OutlineNode(
        node_id=f"N-{i}",
        level=1,
        order=i,
        title=title,
        objective="근거 기반 분석",
        analysis_questions=[],
        expected_length=500,
        source_scope=[],
        required_evidence_types=[],
        planned_visuals=[],
    )


def test_outline_gate_rejects_forbidden_top_level():
    plan = ReportPlan(
        title="t",
        purpose="p",
        target_reader="r",
        report_summary="s",
        outline=[
            _node(1, "분석 개요"),
            _node(2, "PDA"),
            _node(3, "프로세스"),
            _node(4, "성과"),
            _node(5, "한계"),
        ],
    )
    gate = validate_outline(plan)
    assert gate.passed is False
    assert any("forbidden top-level heading: PDA" in r for r in gate.reasons)
