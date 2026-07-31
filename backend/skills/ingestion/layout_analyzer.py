"""Page type classification and reading-order layout helpers.

Heuristics only — no domain keywords.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.enums import PageType
from backend.skills.ingestion.layout_rebuild import (
    reconstruct_row_pairs,
    sort_reading_order,
    structure_column_sections,
)
from backend.skills.ingestion.pdf_parser import RawPage, RawTextBlock


@dataclass
class LayoutResult:
    page_type: PageType
    blocks: list[RawTextBlock]
    needs_ocr: bool
    needs_page_image: bool


def classify_page(page: RawPage, *, min_text_chars: int = 40) -> LayoutResult:
    text_len = len(page.full_text.strip())
    text_blocks = [
        b for b in page.blocks if b.block_type in {"TEXT", "OCR", "TABLE"}
    ]
    image_blocks = [b for b in page.blocks if b.block_type == "IMAGE"]

    page_area = max(page.width * page.height, 1.0)
    image_area = sum(_area(b.bbox) for b in image_blocks)
    image_ratio = image_area / page_area

    has_drawings = page.drawing_count >= 4
    dense_images = image_ratio >= 0.35 or (len(image_blocks) >= 1 and image_ratio >= 0.2)
    many_images = page.image_count >= 2 or len(image_blocks) >= 2
    sparse_text = text_len < min_text_chars
    short_text = text_len < 250
    medium_text = min_text_chars <= text_len < 400
    kv_blocks = _count_kv_shaped_blocks(page)

    needs_page_image = True

    if (sparse_text or short_text) and (dense_images or has_drawings or many_images):
        page_type = PageType.DIAGRAM
    elif sparse_text and not page.text_layer_available:
        page_type = PageType.SCANNED
    elif (
        _looks_like_table(page.full_text)
        or _looks_like_two_column(page)
        or kv_blocks >= 3
    ):
        page_type = PageType.TABLE if not dense_images else PageType.MIXED
    elif _looks_like_chart(page.full_text) or (
        medium_text and dense_images and _has_metric_tokens(page.full_text)
    ):
        page_type = PageType.CHART if not has_drawings else PageType.MIXED
    elif dense_images and medium_text:
        page_type = PageType.MIXED
    elif dense_images and has_drawings:
        page_type = PageType.DIAGRAM
    else:
        page_type = PageType.TEXT

    # OCR only when the text layer is genuinely thin (avoid TEXT+OCR duplicates)
    needs_ocr = False
    if page_type == PageType.SCANNED:
        needs_ocr = True
    elif page_type == PageType.DIAGRAM and text_len < 120:
        needs_ocr = True
    elif sparse_text and not page.text_layer_available:
        needs_ocr = True
    elif sparse_text and (dense_images or many_images) and text_len < 80:
        needs_ocr = True

    ordered = sort_reading_order(text_blocks or page.blocks, page.width)
    # Always try KV / table pairing (multiline or left-right)
    ordered = reconstruct_row_pairs(ordered, page.width)
    # Column section markers only for narrow-node diagrams (flowchart/architecture)
    if page_type in {PageType.DIAGRAM, PageType.MIXED, PageType.CHART}:
        table_n = sum(1 for b in ordered if b.block_type == "TABLE")
        avg_w = 0.0
        if ordered:
            avg_w = sum(max(1.0, b.bbox[2] - b.bbox[0]) for b in ordered) / len(ordered)
        if table_n < 2 and avg_w < page.width * 0.25 and len(ordered) >= 6:
            ordered = structure_column_sections(ordered, page.width)

    return LayoutResult(
        page_type=page_type,
        blocks=ordered,
        needs_ocr=needs_ocr,
        needs_page_image=needs_page_image,
    )


def _area(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _count_kv_shaped_blocks(page: RawPage) -> int:
    """Blocks whose first line is a short label and the rest is longer body."""
    n = 0
    for b in page.blocks:
        if b.block_type not in {"TEXT", "OCR"}:
            continue
        lines = [ln.strip() for ln in (b.text or "").splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        head, body = lines[0], " ".join(lines[1:])
        if len(head) <= 24 and len(body) >= max(18, len(head) * 2):
            n += 1
    return n


def _looks_like_table(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    sep_lines = sum(1 for ln in lines if ln.count("|") >= 2 or ln.count("\t") >= 2)
    return sep_lines >= 2


def _looks_like_two_column(page: RawPage) -> bool:
    """Many short left labels + longer right texts → table-ish layout."""
    texts = [b for b in page.blocks if b.block_type == "TEXT" and b.text.strip()]
    if len(texts) < 6:
        return False
    mid = page.width / 2.0
    left = [b for b in texts if b.bbox[2] < mid]
    right = [b for b in texts if b.bbox[0] > mid * 0.9]
    if len(left) < 3 or len(right) < 3:
        return False
    avg_l = sum(len(b.text) for b in left) / len(left)
    avg_r = sum(len(b.text) for b in right) / len(right)
    return avg_l < avg_r * 0.6


def _looks_like_chart(text: str) -> bool:
    lower = text.lower()
    markers = ("%", "증가", "감소", "향상", "baseline", "before", "after", "vs")
    hits = sum(1 for m in markers if m in lower or m in text)
    return hits >= 2 and any(ch.isdigit() for ch in text)


def _has_metric_tokens(text: str) -> bool:
    return any(ch.isdigit() for ch in text) and ("%" in text or "+" in text or "-" in text)
