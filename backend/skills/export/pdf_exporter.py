"""PDF exporter via fpdf2 (Korean font when available)."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF
from fpdf.errors import FPDFException

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        try:
            self.set_font("Nanum", size=8)
        except Exception:
            self.set_font("Helvetica", size=8)
        self.cell(0, 10, f"{self.page_no()}", align="C")


def export_pdf(
    path: Path,
    markdown: str,
    *,
    title: str,
    image_root: Path | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = ReportPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    if Path(FONT).exists():
        pdf.add_font("Nanum", "", FONT)
        pdf.set_font("Nanum", size=11)
        font = "Nanum"
    else:
        pdf.set_font("Helvetica", size=11)
        font = "Helvetica"

    pdf.add_page()
    pdf.set_font(font, size=16)
    _safe_multicell(pdf, title)
    pdf.ln(4)
    pdf.set_font(font, size=11)

    in_code = False
    for block in markdown.split("\n"):
        line = block.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            pdf.ln(3)
            pdf.set_font(font, size=13)
            _safe_multicell(pdf, line[3:].strip())
            pdf.set_font(font, size=11)
            continue
        if line.startswith("### "):
            pdf.set_font(font, size=12)
            _safe_multicell(pdf, line[4:].strip())
            pdf.set_font(font, size=11)
            continue
        img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if img and image_root is not None:
            img_path = image_root / Path(img.group(2)).name
            if img_path.is_file():
                pdf.ln(2)
                # Ensure enough room
                if pdf.get_y() > 240:
                    pdf.add_page()
                pdf.image(str(img_path), w=min(170, pdf.epw))
                pdf.ln(2)
                continue
        if line.startswith("|"):
            # compact table row
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            line = " / ".join(cells)

        text = re.sub(r"[*`_]", "", line)
        text = text.replace("\u00a0", " ").strip()
        if not text:
            continue
        _safe_multicell(pdf, text)

    pdf.output(str(path))
    return path


def _safe_multicell(pdf: FPDF, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    # Wrap very long tokens
    text = re.sub(r"(\S{80})", r"\1 ", text)
    try:
        pdf.multi_cell(pdf.epw, 6, text)
    except FPDFException:
        pdf.set_x(pdf.l_margin)
        try:
            pdf.multi_cell(pdf.epw, 6, text[:500])
        except FPDFException:
            pdf.ln(6)
