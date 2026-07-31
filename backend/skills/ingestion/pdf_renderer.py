"""Render PDF pages to PNG via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz

from backend.config import settings


def render_page(
    pdf_path: str | Path,
    page_number: int,
    dest: str | Path,
    *,
    dpi: int | None = None,
) -> Path:
    """Render 1-based page_number to dest PNG. Returns dest path."""
    dpi = dpi or settings.pdf_render_dpi
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_number - 1]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(dest))
    finally:
        doc.close()
    return dest


def render_all_pages(
    pdf_path: str | Path,
    pages_dir: str | Path,
    *,
    dpi: int | None = None,
    page_numbers: list[int] | None = None,
) -> dict[int, Path]:
    pages_dir = Path(pages_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    out: dict[int, Path] = {}
    try:
        indices = page_numbers or list(range(1, len(doc) + 1))
        for n in indices:
            dest = pages_dir / f"page-{n:04d}.png"
            render_page(pdf_path, n, dest, dpi=dpi)
            out[n] = dest
    finally:
        doc.close()
    return out
