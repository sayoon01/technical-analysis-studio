"""Layout rebuild helpers — domain-agnostic."""

from backend.skills.ingestion.layout_rebuild import (
    _cluster_columns,
    _infer_column_split,
    _promote_multiline_kv,
    reconstruct_row_pairs,
    sort_reading_order,
    structure_column_sections,
)
from backend.skills.ingestion.pdf_parser import RawTextBlock


def _b(text: str, x0: float, y0: float, x1: float, y1: float) -> RawTextBlock:
    return RawTextBlock(text=text, bbox=(x0, y0, x1, y1), block_type="TEXT")


def test_sort_reading_order_rows():
    blocks = [
        _b("B", 200, 50, 300, 70),
        _b("A", 20, 50, 80, 70),
        _b("C", 20, 120, 80, 140),
    ]
    ordered = sort_reading_order(blocks, 400)
    assert [b.text for b in ordered] == ["A", "B", "C"]


def test_sort_reading_order_columns():
    # two vertical bands → column-major (left col top-to-bottom, then right)
    blocks = [
        _b("R1", 300, 40, 360, 60),
        _b("L1", 40, 40, 100, 60),
        _b("R2", 300, 100, 360, 120),
        _b("L2", 40, 100, 100, 120),
        _b("R3", 300, 160, 360, 180),
        _b("L3", 40, 160, 100, 180),
    ]
    ordered = sort_reading_order(blocks, 400)
    assert [b.text for b in ordered] == ["L1", "L2", "L3", "R1", "R2", "R3"]


def test_row_pair_uses_gap_not_midpage():
    blocks = [
        _b("기능A", 30, 80, 110, 100),
        _b("긴 설명 내용입니다 여기 더 길게", 160, 80, 480, 100),
        _b("기능B", 30, 130, 110, 150),
        _b("또다른 설명 본문입니다", 160, 130, 450, 150),
        _b("기능C", 30, 180, 110, 200),
        _b("세번째 설명 본문입니다", 160, 180, 440, 200),
    ]
    split = _infer_column_split(blocks, 600)
    assert split is not None
    assert 120 < split < 250
    out = reconstruct_row_pairs(blocks, 600)
    tables = [b for b in out if b.block_type == "TABLE"]
    assert any("기능A |" in b.text for b in tables)
    assert any("기능B |" in b.text for b in tables)
    # originals replaced, not duplicated
    assert not any(b.text == "기능A" for b in out)


def test_multiline_kv_promoted():
    blocks = [
        _b("기능\n세부내용", 40, 40, 400, 70),
        _b("PDA실적등록\n앱을 새로 개발하여 반응속도를 개선함", 40, 100, 500, 140),
        _b("현황판\n실시간으로 현장 실적을 집계하여 표시함", 40, 160, 500, 200),
        _b("PDA\nPDA\nPDA\nPDA", 40, 220, 200, 260),
    ]
    out = _promote_multiline_kv(blocks)
    assert out[0].block_type == "TABLE"
    assert out[0].text == "기능 | 세부내용"
    assert out[1].text.startswith("PDA실적등록 |")
    assert out[2].text.startswith("현황판 |")
    assert " · " in out[3].text


def test_structure_column_sections_marks_headers():
    blocks = [
        _b("연계시스템", 40, 40, 120, 60),
        _b("Web하드", 40, 100, 120, 120),
        _b("주문신청", 40, 160, 120, 180),
        _b("MES", 300, 40, 360, 60),
        _b("작업지시", 300, 100, 380, 120),
        _b("생산실적", 300, 160, 380, 180),
    ]
    out = structure_column_sections(blocks, 500)
    markers = [b for b in out if b.block_type == "STRUCTURE"]
    assert len(markers) >= 2
    assert any("연계시스템" in b.text for b in markers)
    assert any("MES" in b.text for b in markers)


def test_cluster_columns_gap():
    blocks = [
        _b("A", 40, 40, 100, 60),
        _b("B", 40, 100, 100, 120),
        _b("C", 300, 40, 360, 60),
        _b("D", 300, 100, 360, 120),
    ]
    cols = _cluster_columns(blocks, 400)
    assert len(cols) == 2
    assert {b.text for b in cols[0]} == {"A", "B"}
    assert {b.text for b in cols[1]} == {"C", "D"}
