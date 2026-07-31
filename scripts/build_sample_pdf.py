"""Build a multi-page synthetic PDF resembling mixed presentation content."""

from __future__ import annotations

from pathlib import Path

import fitz

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def build_sample_pdf(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    _text_page(doc, "클라우드 기반 가공철근 MES 구축 사례\nD'MES 솔루션 소개")
    for i in range(2, 12):
        _text_page(doc, f"기능 소개 페이지 {i}\n생산실적 수집 및 재고 관리 개요")

    _text_page(
        doc,
        "기존 MES 시스템의 문제와 추진 배경\n"
        "인프라 노후화\n생산실적 데이터 누락\n수기 입력\n계량시스템 미연계\n클레임 문제",
    )

    page = doc.new_page(width=595, height=842)
    _insert(page, (50, 40), "주문부터 생산·출하까지의 업무절차", 14)
    _draw_flow(page)

    page = doc.new_page(width=595, height=842)
    _insert(page, (50, 40), "시스템 구성도", 14)
    _draw_architecture(page)

    _text_page(
        doc,
        "기존 방식과 구축 후 변경사항\n"
        "기존: 수기 실적 등록 | 구축후: PDA 실적 등록\n"
        "기존: 계량 미연계 | 구축후: 무인계량대 연계",
    )

    _text_page(
        doc,
        "구축 효과 (정량)\n"
        "시간당 생산량 8% 증가\n"
        "출하 클레임 60% 감소\n"
        "재공재고 33% 감소\n"
        "측정: 월간 생산실적 기준",
    )
    _text_page(
        doc,
        "납기 준수율 24% 향상\n"
        "측정방법: 출하 예정일 이내 실제 출하량을 전체 출하량으로 나눈 값",
    )
    _text_page(doc, "정성 효과\n안정성 향상\n확장성 확보\n보안성 강화")

    doc.save(str(dest))
    doc.close()
    return dest


def _insert(page: fitz.Page, point: tuple[float, float], text: str, size: float) -> None:
    page.insert_font(fontname="nanum", fontfile=FONT)
    page.insert_text(point, text, fontsize=size, fontname="nanum")


def _text_page(doc: fitz.Document, text: str) -> None:
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="nanum", fontfile=FONT)
    y = 60
    for line in text.split("\n"):
        page.insert_text((50, y), line, fontsize=12, fontname="nanum")
        y += 22


def _draw_flow(page: fitz.Page) -> None:
    page.insert_font(fontname="nanum", fontfile=FONT)
    boxes = [
        (60, 120, "주문생성"),
        (200, 120, "생산지시"),
        (340, 120, "실적처리"),
        (480, 120, "검사"),
        (60, 260, "포장"),
        (200, 260, "제품출하"),
        (340, 260, "재고반영"),
        (480, 260, "마감"),
    ]
    for x, y, label in boxes:
        rect = fitz.Rect(x, y, x + 90, y + 36)
        page.draw_rect(rect, color=(0, 0, 0), width=1)
        page.insert_text((x + 8, y + 22), label, fontsize=9, fontname="nanum")
    # connectors
    for x0, x1, y in ((150, 200, 138), (290, 340, 138), (430, 480, 138)):
        page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), width=1)
    for x0, x1, y in ((150, 200, 278), (290, 340, 278), (430, 480, 278)):
        page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), width=1)
    page.draw_line(fitz.Point(105, 156), fitz.Point(105, 260), width=1)


def _draw_architecture(page: fitz.Page) -> None:
    page.insert_font(fontname="nanum", fontfile=FONT)
    nodes = [
        (220, 80, "클라우드 MES"),
        (40, 220, "G스틸 본사"),
        (220, 220, "네이버 클라우드"),
        (400, 220, "가공공장"),
        (400, 360, "PDA"),
        (40, 360, "사용자 PC"),
        (220, 360, "VPN"),
        (400, 480, "무인계량대"),
    ]
    for x, y, label in nodes:
        rect = fitz.Rect(x, y, x + 130, y + 40)
        page.draw_rect(rect, color=(0, 0, 0), width=1.5)
        page.insert_text((x + 8, y + 25), label, fontsize=10, fontname="nanum")
    edges = [
        ((285, 120), (105, 220)),
        ((285, 120), (285, 220)),
        ((285, 120), (465, 220)),
        ((105, 260), (105, 360)),
        ((465, 260), (465, 360)),
        ((285, 260), (285, 360)),
        ((465, 400), (465, 480)),
    ]
    for a, b in edges:
        page.draw_line(fitz.Point(*a), fitz.Point(*b), width=1)
    page.insert_text((150, 180), "인터넷/VPN", fontsize=9, fontname="nanum")


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_mes.pdf"
    build_sample_pdf(out)
    print(out)
