"""Build a small addendum PDF focused on delivery-rate metrics (for V2 impact)."""

from __future__ import annotations

from pathlib import Path

import fitz

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def build_delivery_addendum(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="nanum", fontfile=FONT)
    y = 60
    for line in [
        "납기 준수율 상세 산정 조건",
        "납기 준수율 24% 향상",
        "측정방법: 출하 예정일 이내 실제 출하량을 전체 출하량으로 나눈 값",
        "산정 기간: 구축 후 6개월",
        "제외: 고객 사유 연기는 모수에서 제외",
    ]:
        page.insert_text((50, y), line, fontsize=12, fontname="nanum")
        y += 24
    doc.save(str(dest))
    doc.close()
    return dest


if __name__ == "__main__":
    print(build_delivery_addendum(Path("tests/fixtures/delivery_addendum.pdf")))
