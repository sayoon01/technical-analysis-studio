"""Plain text / markdown ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.skills.ingestion.pdf_parser import RawPage, RawTextBlock


@dataclass
class TextDocument:
    pages: list[RawPage]


def parse_text_file(path: str | Path) -> TextDocument:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # Split on form-feed or large blank gaps into pseudo-pages
    chunks = [c.strip() for c in text.split("\f") if c.strip()]
    if len(chunks) <= 1:
        # Paragraph grouping into pages of ~3000 chars
        chunks = _split_by_size(text, 3000)

    pages: list[RawPage] = []
    for i, chunk in enumerate(chunks, start=1):
        block = RawTextBlock(
            text=chunk,
            bbox=(0.0, 0.0, 612.0, 792.0),
            block_type="TEXT",
            confidence=1.0,
        )
        pages.append(
            RawPage(
                page_number=i,
                width=612.0,
                height=792.0,
                text_layer_available=True,
                full_text=chunk,
                blocks=[block],
                image_count=0,
                drawing_count=0,
            )
        )
    return TextDocument(pages=pages)


def _split_by_size(text: str, size: int) -> list[str]:
    text = text.strip()
    if not text:
        return [""]
    parts: list[str] = []
    buf: list[str] = []
    length = 0
    for para in text.split("\n\n"):
        if length + len(para) > size and buf:
            parts.append("\n\n".join(buf).strip())
            buf = [para]
            length = len(para)
        else:
            buf.append(para)
            length += len(para)
    if buf:
        parts.append("\n\n".join(buf).strip())
    return parts or [text]
