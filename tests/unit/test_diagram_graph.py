"""Diagram graph extraction — geometry-based, no domain hardcoding."""

from backend.skills.ingestion.diagram_graph import extract_structure_graph
from backend.skills.ingestion.ocr import correct_ocr_lines, OcrLine
from backend.skills.ingestion.pdf_parser import DrawingPrim, RawTextBlock


def _b(text: str, x0: float, y0: float, x1: float, y1: float, t: str = "TEXT") -> RawTextBlock:
    return RawTextBlock(text=text, bbox=(x0, y0, x1, y1), block_type=t)


def test_column_process_edges():
    blocks = [
        _b("연계시스템", 40, 40, 120, 60),
        _b("Web하드", 40, 100, 120, 120),
        _b("주문신청", 40, 160, 120, 180),
        _b("MES", 300, 40, 360, 60),
        _b("작업지시", 300, 100, 380, 120),
        _b("생산실적", 300, 160, 380, 180),
        _b("고객", 560, 40, 620, 60),
        _b("고객사", 560, 100, 640, 120),
    ]
    g = extract_structure_graph(blocks, [], page_width=700, page_height=400, page_title_hint="흐름도")
    assert g is not None
    assert len(g.nodes) >= 6
    assert len(g.edges) >= 3
    assert g.kind in {"PROCESS", "ARCHITECTURE"}


def test_line_edges_and_rect_groups():
    blocks = [
        _b("클라우드", 40, 40, 160, 60),
        _b("MES", 60, 100, 120, 120),
        _b("본사", 400, 40, 480, 60),
        _b("사용자PC", 420, 100, 500, 120),
        _b("VPN", 220, 80, 260, 100),
    ]
    drawings = [
        DrawingPrim(kind="rect", bbox=(30, 30, 180, 200), points=[]),
        DrawingPrim(kind="rect", bbox=(390, 30, 520, 200), points=[]),
        DrawingPrim(
            kind="line",
            bbox=(160, 90, 400, 95),
            points=[(160, 90), (400, 95)],
        ),
    ]
    g = extract_structure_graph(
        blocks, drawings, page_width=600, page_height=300, page_title_hint="구성도"
    )
    assert g is not None
    assert g.kind == "ARCHITECTURE"
    assert len(g.groups) >= 1
    assert any(e.confidence >= 0.8 for e in g.edges) or len(g.edges) >= 1


def test_ocr_lexicon_correction():
    lex = ["G스틸", "생산실적처리", "작업지시"]
    lines = [
        OcrLine(text="G스템", bbox=(0, 0, 10, 10), confidence=0.5),
        OcrLine(text="생산신적처리", bbox=(0, 20, 10, 30), confidence=0.5),
    ]
    fixed = correct_ocr_lines(lines, lex, max_distance=2)
    assert fixed[0].text == "G스틸"
    assert fixed[1].text == "생산실적처리"
