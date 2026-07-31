"""Build a second-domain sample PDF (NPU/GPU thermal) for generality tests."""

from __future__ import annotations

from pathlib import Path

import fitz

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def build_npu_pdf(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    _text(
        doc,
        "온디바이스 NPU·GPU 열관리 기술 보고서\n모바일 SoC 전력·온도 제어",
    )
    _text(
        doc,
        "기존 열관리의 문제\n"
        "고부하 시 스로틀링 빈발\n온도 센서 해상도 부족\n동적 전압 스케일링 미흡",
    )
    page = doc.new_page(width=595, height=842)
    _font(page)
    page.insert_text((50, 40), "열관리 제어 흐름", fontsize=14, fontname="nanum")
    for i, label in enumerate(["센서수집", "예측모델", "DVFS", "냉각제어"]):
        x = 60 + i * 120
        page.draw_rect(fitz.Rect(x, 120, x + 100, 160), width=1)
        page.insert_text((x + 10, 145), label, fontsize=10, fontname="nanum")
        if i < 3:
            page.draw_line(fitz.Point(x + 100, 140), fitz.Point(x + 120, 140))

    page = doc.new_page(width=595, height=842)
    _font(page)
    page.insert_text((50, 40), "하드웨어 구성", fontsize=14, fontname="nanum")
    for x, y, label in [
        (200, 100, "NPU"),
        (80, 240, "GPU"),
        (320, 240, "열센서"),
        (200, 360, "전력관리IC"),
    ]:
        page.draw_rect(fitz.Rect(x, y, x + 110, y + 40), width=1.5)
        page.insert_text((x + 20, y + 25), label, fontsize=11, fontname="nanum")
    page.draw_line(fitz.Point(255, 140), fitz.Point(135, 240))
    page.draw_line(fitz.Point(255, 140), fitz.Point(375, 240))

    _text(
        doc,
        "실험 결과\n"
        "피크 온도 12% 감소\n"
        "스로틀링 발생 45% 감소\n"
        "에너지 효율 9% 향상\n"
        "측정방법: 벤치마크 30분 연속 부하 평균",
    )
    _text(doc, "정성 평가\n안정성 개선\n사용자 체감 성능 향상")
    doc.save(str(dest))
    doc.close()
    return dest


def _font(page: fitz.Page) -> None:
    page.insert_font(fontname="nanum", fontfile=FONT)


def _text(doc: fitz.Document, text: str) -> None:
    page = doc.new_page(width=595, height=842)
    _font(page)
    y = 60
    for line in text.split("\n"):
        page.insert_text((50, y), line, fontsize=12, fontname="nanum")
        y += 22


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_npu.pdf"
    print(build_npu_pdf(out))
