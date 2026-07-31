"""PDF text/block extraction via PyMuPDF."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz


@dataclass
class RawTextBlock:
    text: str
    bbox: tuple[float, float, float, float]
    block_type: str = "TEXT"
    confidence: float = 1.0


@dataclass
class DrawingPrim:
    """Vector primitive from page.get_drawings()."""

    kind: str  # line | rect
    bbox: tuple[float, float, float, float]
    points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class RawPage:
    page_number: int  # 1-based
    width: float
    height: float
    text_layer_available: bool
    full_text: str
    blocks: list[RawTextBlock] = field(default_factory=list)
    image_count: int = 0
    drawing_count: int = 0
    drawings: list[DrawingPrim] = field(default_factory=list)


def open_pdf(path: str | Path) -> fitz.Document:
    return fitz.open(str(path))


def extract_pages(path: str | Path) -> list[RawPage]:
    doc = open_pdf(path)
    try:
        pages: list[RawPage] = []
        for i in range(len(doc)):
            page = doc[i]
            pages.append(_extract_page(page, i + 1))
        return pages
    finally:
        doc.close()


def _extract_page(page: fitz.Page, page_number: int) -> RawPage:
    width, height = float(page.rect.width), float(page.rect.height)
    dict_data = page.get_text("dict")
    blocks: list[RawTextBlock] = []
    texts: list[str] = []

    for block in dict_data.get("blocks", []):
        btype = block.get("type", 0)
        bbox = tuple(float(x) for x in block.get("bbox", (0, 0, 0, 0)))
        if btype == 0:  # text
            lines = []
            for line in block.get("lines", []):
                spans = [s.get("text", "") for s in line.get("spans", [])]
                parts: list[str] = []
                for s in spans:
                    if not s:
                        continue
                    if parts and not parts[-1].endswith((" ", "\n")) and not s.startswith(" "):
                        if parts[-1][-1].isalnum() and s[0].isalnum():
                            parts.append(" ")
                    parts.append(s)
                line_text = "".join(parts).strip()
                if line_text:
                    lines.append(line_text)
            text = "\n".join(lines).strip()
            if text:
                blocks.append(
                    RawTextBlock(text=text, bbox=bbox, block_type="TEXT", confidence=1.0)
                )
                texts.append(text)
        elif btype == 1:  # image
            blocks.append(
                RawTextBlock(
                    text="[IMAGE]",
                    bbox=bbox,
                    block_type="IMAGE",
                    confidence=1.0,
                )
            )

    full_text = "\n".join(texts).strip()
    if not full_text:
        plain = page.get_text("text").strip()
        if plain:
            full_text = plain
            blocks.append(
                RawTextBlock(
                    text=plain,
                    bbox=(0.0, 0.0, width, height),
                    block_type="TEXT",
                    confidence=0.9,
                )
            )

    raw_drawings = page.get_drawings()
    drawings = _extract_drawing_prims(raw_drawings)
    images = page.get_images(full=True)

    return RawPage(
        page_number=page_number,
        width=width,
        height=height,
        text_layer_available=bool(full_text),
        full_text=full_text,
        blocks=blocks,
        image_count=len(images),
        drawing_count=len(raw_drawings),
        drawings=drawings,
    )


def _extract_drawing_prims(raw_drawings: list) -> list[DrawingPrim]:
    out: list[DrawingPrim] = []
    for d in raw_drawings or []:
        rect = d.get("rect")
        rbbox = None
        if rect is not None:
            rbbox = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        for it in d.get("items") or []:
            op = it[0]
            if op == "l" and len(it) >= 3:
                p1, p2 = it[1], it[2]
                x0 = float(min(p1.x, p2.x))
                y0 = float(min(p1.y, p2.y))
                x1 = float(max(p1.x, p2.x))
                y1 = float(max(p1.y, p2.y))
                # skip tiny ticks
                if (x1 - x0) + (y1 - y0) < 8:
                    continue
                out.append(
                    DrawingPrim(
                        kind="line",
                        bbox=(x0, y0, x1, y1),
                        points=[(float(p1.x), float(p1.y)), (float(p2.x), float(p2.y))],
                    )
                )
            elif op == "re" and len(it) >= 2:
                r = it[1]
                bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 40:
                    continue
                out.append(DrawingPrim(kind="rect", bbox=bbox, points=[]))
            elif op == "c" and len(it) >= 5:
                # cubic: use endpoints as a soft line
                p1, p4 = it[1], it[4]
                out.append(
                    DrawingPrim(
                        kind="line",
                        bbox=(
                            float(min(p1.x, p4.x)),
                            float(min(p1.y, p4.y)),
                            float(max(p1.x, p4.x)),
                            float(max(p1.y, p4.y)),
                        ),
                        points=[(float(p1.x), float(p1.y)), (float(p4.x), float(p4.y))],
                    )
                )
        # filled shape without items — use drawing rect as container candidate
        if rbbox and not any(it[0] == "re" for it in (d.get("items") or [])):
            area = (rbbox[2] - rbbox[0]) * (rbbox[3] - rbbox[1])
            if area >= 200:
                out.append(DrawingPrim(kind="rect", bbox=rbbox, points=[]))
    return out
