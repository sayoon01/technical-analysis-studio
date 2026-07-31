"""Generic layout reconstruction from bboxes — no domain keywords.

Improves structure (not just flat dump):
- reading order: multi-column → column-major; else row-major
- table / KV: left|right row pairs, or first-line label + body in one block
"""

from __future__ import annotations

import re

from backend.skills.ingestion.pdf_parser import RawTextBlock


def sort_reading_order(
    blocks: list[RawTextBlock], page_width: float
) -> list[RawTextBlock]:
    """Prefer column-major when parallel vertical bands exist; else row-major."""
    textish = [
        b
        for b in blocks
        if b.block_type in {"TEXT", "OCR", "TABLE", "STRUCTURE"}
        and (b.text or "").strip()
    ]
    others = [b for b in blocks if b not in textish]
    if not textish:
        return list(blocks)

    columns = _cluster_columns(textish, page_width)
    if _is_multi_column(columns, page_width):
        ordered: list[RawTextBlock] = []
        for col in columns:
            ordered.extend(
                sorted(col, key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2.0, b.bbox[0]))
            )
        return ordered + others

    rows = _cluster_rows(textish)
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: b.bbox[0]))
    return ordered + others


def reconstruct_row_pairs(
    blocks: list[RawTextBlock], page_width: float
) -> list[RawTextBlock]:
    """Restore label↔value structure.

    1) Multiline blocks: short first line + longer body → `label | body` (TABLE)
    2) Separate left/right cells on the same row band → `left | right` (TABLE)
    Paired source blocks are replaced (not duplicated).
    """
    blocks = _promote_multiline_kv(blocks)

    textish = [
        b
        for b in blocks
        if b.block_type in {"TEXT", "OCR"} and (b.text or "").strip()
    ]
    if len(textish) < 4:
        return blocks

    split_x = _infer_column_split(textish, page_width)
    if split_x is None:
        return blocks

    rows = _cluster_rows(textish)
    paired_ids: set[int] = set()
    extras: list[RawTextBlock] = []
    for row in rows:
        left = [b for b in row if ((b.bbox[0] + b.bbox[2]) / 2.0) < split_x]
        right = [b for b in row if ((b.bbox[0] + b.bbox[2]) / 2.0) >= split_x]
        if not left or not right:
            continue
        left_t = " ".join(b.text.strip() for b in sorted(left, key=lambda b: b.bbox[0]))
        right_t = " ".join(b.text.strip() for b in sorted(right, key=lambda b: b.bbox[0]))
        if not left_t or not right_t:
            continue
        if "|" in left_t or "|" in right_t:
            continue
        if len(left_t) > len(right_t) or len(left_t) > 40:
            continue
        y0 = min(b.bbox[1] for b in row)
        y1 = max(b.bbox[3] for b in row)
        extras.append(
            RawTextBlock(
                text=f"{left_t} | {right_t}",
                bbox=(min(b.bbox[0] for b in row), y0, max(b.bbox[2] for b in row), y1),
                block_type="TABLE",
                confidence=0.85,
            )
        )
        paired_ids.update(id(b) for b in left + right)

    if not extras:
        return blocks

    kept = [b for b in blocks if id(b) not in paired_ids]
    return sort_reading_order(kept + extras, page_width)


def structure_column_sections(
    blocks: list[RawTextBlock], page_width: float
) -> list[RawTextBlock]:
    """For parallel multi-column diagrams: insert section markers per column."""
    textish = [
        b
        for b in blocks
        if b.block_type in {"TEXT", "OCR", "TABLE"} and (b.text or "").strip()
    ]
    others = [b for b in blocks if b not in textish]
    columns = _cluster_columns(textish, page_width)
    if not _is_multi_column(columns, page_width):
        return blocks

    ordered: list[RawTextBlock] = []
    for col in columns:
        col_sorted = sorted(
            col, key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2.0, b.bbox[0])
        )
        if not col_sorted:
            continue
        head = col_sorted[0]
        head_line = (head.text or "").splitlines()[0].strip()
        # Skip full-width titles / already-paired table rows as section headers
        head_w = head.bbox[2] - head.bbox[0]
        if (
            len(col_sorted) >= 2
            and 1 < len(head_line) <= 16
            and "|" not in head_line
            and head_w < page_width * 0.35
            and not head_line.startswith("§")
        ):
            x0, y0, x1, _y1 = head.bbox
            ordered.append(
                RawTextBlock(
                    text=f"§ {head_line}",
                    bbox=(x0, max(0.0, y0 - 1.0), x1, y0),
                    block_type="STRUCTURE",
                    confidence=0.7,
                )
            )
        ordered.extend(col_sorted)
    return ordered + others


def _promote_multiline_kv(blocks: list[RawTextBlock]) -> list[RawTextBlock]:
    """`기능\\n세부설명...` inside one bbox → TABLE `기능 | 세부설명`."""
    out: list[RawTextBlock] = []
    for b in blocks:
        if b.block_type not in {"TEXT", "OCR"} or not (b.text or "").strip():
            out.append(b)
            continue
        lines = [ln.strip() for ln in b.text.splitlines() if ln.strip()]
        if len(lines) < 2:
            out.append(b)
            continue

        # Two short header cells (기능 / 세부내용) → column headers
        if len(lines) == 2 and len(lines[0]) <= 16 and len(lines[1]) <= 16:
            # stacked quantities (1,931억원 / 1,762억원) are NOT headers
            if _looks_like_quantity(lines[0]) and _looks_like_quantity(lines[1]):
                out.append(
                    RawTextBlock(
                        text="\n".join(lines),
                        bbox=b.bbox,
                        block_type=b.block_type,
                        confidence=b.confidence,
                    )
                )
                continue
            out.append(
                RawTextBlock(
                    text=f"{lines[0]} | {lines[1]}",
                    bbox=b.bbox,
                    block_type="TABLE",
                    confidence=min(0.9, b.confidence or 1.0),
                )
            )
            continue

        # Repeated short labels (PDA×4, year ticks) — join, not KV
        if _repeated_short_labels(lines):
            out.append(
                RawTextBlock(
                    text=" · ".join(lines),
                    bbox=b.bbox,
                    block_type=b.block_type,
                    confidence=b.confidence,
                )
            )
            continue

        head, body = lines[0], " ".join(lines[1:])
        if (
            len(head) <= 24
            and len(body) >= max(18, len(head) * 2)
            and "|" not in b.text
            and not head.endswith((".", ",", ";"))
        ):
            out.append(
                RawTextBlock(
                    text=f"{head} | {body}",
                    bbox=b.bbox,
                    block_type="TABLE",
                    confidence=min(0.9, b.confidence or 1.0),
                )
            )
            continue
        out.append(b)
    return out


def _repeated_short_labels(lines: list[str]) -> bool:
    """True for PDA/PDA/PDA or [a]/[b]/[c] style repeats — not distinct headers."""
    if len(lines) < 2 or any(len(ln) > 16 for ln in lines):
        return False
    lengths = [len(ln) for ln in lines]
    if max(lengths) - min(lengths) > 6:
        return False
    norms = ["".join(ln.split()).lower() for ln in lines]
    if len(set(norms)) == 1:
        return True
    if all(ln.startswith("[") and ln.endswith("]") for ln in lines):
        return True
    if all(ln.isdigit() and len(ln) == 4 for ln in lines):
        return True
    return False


def _looks_like_quantity(text: str) -> bool:
    return bool(
        re.match(
            r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*"
            r"(?:%|퍼센트|명|원|천원|만원|억원|조원|달러|건|개|회|대|톤|kg|t|ton)$",
            text.strip(),
            re.IGNORECASE,
        )
    )


def _cluster_columns(
    blocks: list[RawTextBlock], page_width: float, *, x_tol: float | None = None
) -> list[list[RawTextBlock]]:
    if not blocks:
        return []
    widths = [max(12.0, b.bbox[2] - b.bbox[0]) for b in blocks]
    tol = x_tol if x_tol is not None else max(28.0, sorted(widths)[len(widths) // 2] * 0.9)
    tol = min(tol, page_width * 0.12)
    ordered = sorted(blocks, key=lambda b: ((b.bbox[0] + b.bbox[2]) / 2.0, b.bbox[1]))
    cols: list[list[RawTextBlock]] = []
    centers: list[float] = []
    for b in ordered:
        cx = (b.bbox[0] + b.bbox[2]) / 2.0
        if not cols or abs(cx - centers[-1]) > tol:
            cols.append([b])
            centers.append(cx)
        else:
            cols[-1].append(b)
            centers[-1] = sum((x.bbox[0] + x.bbox[2]) / 2.0 for x in cols[-1]) / len(
                cols[-1]
            )
    paired = sorted(zip(centers, cols), key=lambda t: t[0])
    return [c for _, c in paired]


def _is_multi_column(
    columns: list[list[RawTextBlock]], page_width: float
) -> bool:
    """Parallel narrow columns (flowcharts), not wide dashboard/table blobs."""
    flat = [b for c in columns for b in c]
    if len(flat) < 6:
        return False
    # Tables already express structure — don't zigzag-sort them
    if sum(1 for b in flat if b.block_type == "TABLE") >= 2:
        return False
    avg_w = sum(max(1.0, b.bbox[2] - b.bbox[0]) for b in flat) / len(flat)
    if avg_w > page_width * 0.28:
        return False

    rich = [c for c in columns if len(c) >= 2]
    if len(rich) < 2:
        return False

    def yspan(col: list[RawTextBlock]) -> tuple[float, float]:
        return min(b.bbox[1] for b in col), max(b.bbox[3] for b in col)

    spans = [yspan(c) for c in rich]
    overlap_hits = 0
    for i, (a0, a1) in enumerate(spans):
        for b0, b1 in spans[i + 1 :]:
            inter = min(a1, b1) - max(a0, b0)
            union = max(a1, b1) - min(a0, b0)
            if union > 0 and inter / union >= 0.35:
                overlap_hits += 1
    return overlap_hits >= 1


def _infer_column_split(
    blocks: list[RawTextBlock], page_width: float
) -> float | None:
    centers = sorted((b.bbox[0] + b.bbox[2]) / 2.0 for b in blocks)
    lo, hi = page_width * 0.05, page_width * 0.75
    best_gap = 0.0
    best_split = None
    for a, b in zip(centers, centers[1:]):
        mid = (a + b) / 2.0
        if mid < lo or mid > hi:
            continue
        gap = b - a
        if gap > best_gap:
            best_gap = gap
            best_split = mid
    if best_split is None or best_gap < max(30.0, page_width * 0.06):
        return None
    return best_split


def _cluster_rows(
    blocks: list[RawTextBlock], *, y_tol: float | None = None
) -> list[list[RawTextBlock]]:
    if not blocks:
        return []
    heights = [max(8.0, b.bbox[3] - b.bbox[1]) for b in blocks]
    tol = y_tol if y_tol is not None else max(10.0, sorted(heights)[len(heights) // 2] * 0.6)
    ordered = sorted(blocks, key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2.0, b.bbox[0]))
    rows: list[list[RawTextBlock]] = []
    centers: list[float] = []
    for b in ordered:
        cy = (b.bbox[1] + b.bbox[3]) / 2.0
        if not rows or abs(cy - centers[-1]) > tol:
            rows.append([b])
            centers.append(cy)
        else:
            rows[-1].append(b)
            centers[-1] = sum((x.bbox[1] + x.bbox[3]) / 2.0 for x in rows[-1]) / len(
                rows[-1]
            )
    return rows
