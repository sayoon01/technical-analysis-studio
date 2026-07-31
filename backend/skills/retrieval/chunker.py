"""Chunk content blocks for retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    page_number: int
    block_ids: list[str]
    text: str
    page_type: str | None = None


def chunk_blocks(
    blocks: list[dict],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Chunk]:
    """Merge adjacent same-page blocks into chunks under max_chars."""
    if not blocks:
        return []

    chunks: list[Chunk] = []
    by_page: dict[int, list[dict]] = {}
    for b in blocks:
        by_page.setdefault(b["page_number"], []).append(b)

    for page_number, page_blocks in sorted(by_page.items()):
        buf_text: list[str] = []
        buf_ids: list[str] = []
        length = 0
        source_id = page_blocks[0]["source_id"]
        page_type = page_blocks[0].get("page_type")

        def flush() -> None:
            nonlocal buf_text, buf_ids, length
            if not buf_text:
                return
            text = "\n".join(buf_text).strip()
            if text:
                chunks.append(
                    Chunk(
                        chunk_id=f"CHK-{uuid.uuid4().hex[:10].upper()}",
                        source_id=source_id,
                        page_number=page_number,
                        block_ids=list(buf_ids),
                        text=text,
                        page_type=page_type,
                    )
                )
            if overlap_chars > 0 and text:
                tail = text[-overlap_chars:]
                buf_text = [tail]
                buf_ids = buf_ids[-1:] if buf_ids else []
                length = len(tail)
            else:
                buf_text, buf_ids, length = [], [], 0

        for b in page_blocks:
            t = (b.get("text") or "").strip()
            if not t or t == "[IMAGE]":
                continue
            if length + len(t) > max_chars and buf_text:
                flush()
            buf_text.append(t)
            buf_ids.append(b["block_id"])
            length += len(t) + 1
        flush()

    return chunks
