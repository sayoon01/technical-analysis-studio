"""Source ingestion pipeline: parse → layout → OCR → blocks → index."""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

from backend.config import settings
from backend.skills.analysis.metric_extractor import extract_metrics_from_text, to_metric_row
from backend.skills.ingestion.diagram_graph import (
    extract_structure_graph,
    refine_structure_with_llm,
    to_structure_row,
)
from backend.skills.ingestion.docx_parser import parse_docx
from backend.skills.ingestion.file_detector import detect_format
from backend.skills.ingestion.hwp_parser import parse_hwp
from backend.skills.ingestion.layout_analyzer import classify_page
from backend.skills.ingestion.ocr import correct_ocr_lines, image_bbox_to_page, ocr_image
from backend.skills.ingestion.pdf_parser import RawPage, RawTextBlock, extract_pages
from backend.skills.ingestion.pdf_renderer import render_page
from backend.skills.ingestion.pptx_parser import parse_pptx
from backend.skills.ingestion.spreadsheet_parser import parse_spreadsheet
from backend.skills.ingestion.text_parser import parse_text_file
from backend.skills.retrieval.chunker import chunk_blocks
from backend.skills.retrieval.vector_search import VectorStore
from backend.storage.file_store import FileStore
from backend.storage.repositories import (
    ContentBlockRepository,
    PageRepository,
    ProjectRepository,
    SourceRepository,
)
from backend.domain.enums import PageType


class SourcePipeline:
    def __init__(
        self,
        conn: sqlite3.Connection,
        file_store: FileStore | None = None,
    ) -> None:
        self.conn = conn
        self.file_store = file_store or FileStore()
        self.projects = ProjectRepository(conn)
        self.sources = SourceRepository(conn)
        self.pages = PageRepository(conn)
        self.blocks = ContentBlockRepository(conn)

    def process_source(self, source_id: str) -> dict:
        source = self.sources.get(source_id)
        if not source:
            raise ValueError(f"Source not found: {source_id}")

        self.sources.update(source_id, status="PROCESSING")
        project_id = source["project_id"]
        path = Path(source["storage_path"])
        fmt = detect_format(source["filename"])

        try:
            raw_pages = self._load_pages(path, fmt)
            self.blocks.delete_for_source(source_id)
            self._clear_metrics(source_id)
            self._clear_structure(source_id)

            all_blocks: list[dict] = []
            ocr_scores: list[float] = []

            for raw in raw_pages:
                layout = classify_page(raw)
                image_path: str | None = None

                if fmt == "pdf":
                    img = self.file_store.page_image_path(
                        project_id, source_id, raw.page_number
                    )
                    render_page(path, raw.page_number, img)
                    image_path = str(img)

                    if layout.needs_ocr and settings.ocr_enabled:
                        ocr = ocr_image(img)
                        if ocr.lines:
                            ocr_scores.append(ocr.confidence)
                            dpi = settings.pdf_render_dpi
                            text_keys = [
                                _norm_key(b.text)
                                for b in raw.blocks
                                if b.block_type == "TEXT" and (b.text or "").strip()
                            ]
                            lexicon = [
                                ln
                                for b in raw.blocks
                                if b.block_type == "TEXT"
                                for ln in (b.text or "").splitlines()
                                if ln.strip()
                            ]
                            corrected = correct_ocr_lines(ocr.lines, lexicon)
                            for line in corrected:
                                if not (line.text or "").strip():
                                    continue
                                if _is_duplicate_of_existing(line.text, text_keys):
                                    continue
                                page_bbox = image_bbox_to_page(line.bbox, dpi=dpi)
                                raw.blocks.append(
                                    RawTextBlock(
                                        text=line.text.strip(),
                                        bbox=page_bbox,
                                        block_type="OCR",
                                        confidence=line.confidence,
                                    )
                                )
                                text_keys.append(_norm_key(line.text))
                            raw.full_text = _page_text_from_blocks(raw.blocks)
                            layout = classify_page(raw)
                        elif ocr.text and not raw.full_text.strip():
                            ocr_scores.append(ocr.confidence)
                            raw.blocks.append(
                                RawTextBlock(
                                    text=ocr.text,
                                    bbox=(0.0, 0.0, raw.width, raw.height),
                                    block_type="OCR",
                                    confidence=ocr.confidence,
                                )
                            )
                            raw.full_text = ocr.text
                            layout = classify_page(raw)

                page_id = f"PG-{source_id}-{raw.page_number:04d}"
                self.pages.upsert(
                    {
                        "page_id": page_id,
                        "source_id": source_id,
                        "page_number": raw.page_number,
                        "page_type": layout.page_type.value,
                        "text_layer_available": raw.text_layer_available,
                        "image_path": image_path,
                        "width": raw.width,
                        "height": raw.height,
                    }
                )

                for order, b in enumerate(layout.blocks):
                    if not (b.text or "").strip() or b.text == "[IMAGE]":
                        continue
                    if b.block_type == "IMAGE":
                        continue
                    block = {
                        "block_id": f"BLK-{uuid.uuid4().hex[:12].upper()}",
                        "source_id": source_id,
                        "page_number": raw.page_number,
                        "block_type": b.block_type,
                        "text": b.text,
                        "bbox": b.bbox,
                        "reading_order": order,
                        "confidence": b.confidence,
                        "page_type": layout.page_type.value,
                    }
                    all_blocks.append(block)

                # Metrics from visual top→bottom order (stable vs column reshuffle)
                metric_blocks = sorted(
                    [
                        b
                        for b in layout.blocks
                        if b.block_type != "STRUCTURE"
                    ],
                    key=lambda b: (
                        (b.bbox[1] + b.bbox[3]) / 2.0 if b.bbox else 0.0,
                        b.bbox[0] if b.bbox else 0.0,
                    ),
                )
                page_text = _page_text_from_blocks(metric_blocks) or raw.full_text
                for metric in extract_metrics_from_text(page_text):
                    row = to_metric_row(
                        metric, source_id=source_id, page_number=raw.page_number
                    )
                    self._insert_metric(row)

                # Diagram / process structure (geometry-first; optional LLM refine)
                if _should_extract_structure(layout, raw):
                    title_hint = None
                    for b in layout.blocks:
                        t = (b.text or "").splitlines()[0].strip() if b.text else ""
                        if 4 <= len(t) <= 40 and b.block_type in {"TEXT", "OCR"}:
                            if (b.bbox[2] - b.bbox[0]) < raw.width * 0.45:
                                title_hint = t
                                break
                    graph = extract_structure_graph(
                        layout.blocks,
                        getattr(raw, "drawings", None) or [],
                        page_width=raw.width,
                        page_height=raw.height,
                        page_title_hint=title_hint,
                    )
                    if graph and len(graph.nodes) >= 3:
                        graph = refine_structure_with_llm(
                            graph, image_path=image_path, page_text=page_text
                        )
                        self._insert_structure(
                            to_structure_row(
                                graph,
                                source_id=source_id,
                                page_number=raw.page_number,
                            )
                        )

            self.blocks.insert_many(all_blocks)

            chunks = chunk_blocks(all_blocks)
            store = VectorStore(project_id)
            store.upsert_chunks(
                [
                    {
                        "chunk_id": c.chunk_id,
                        "source_id": c.source_id,
                        "page_number": c.page_number,
                        "block_ids": c.block_ids,
                        "text": c.text,
                        "page_type": c.page_type,
                    }
                    for c in chunks
                ]
            )

            avg_ocr = sum(ocr_scores) / len(ocr_scores) if ocr_scores else None
            self.sources.update(
                source_id,
                status="READY",
                page_count=len(raw_pages),
                ocr_quality=avg_ocr,
            )

            project = self.projects.get(project_id)
            if project and project["stage"] in {"CREATED", "INGESTING"}:
                self.projects.update_stage(project_id, "ANALYZING")

            return {
                "source_id": source_id,
                "page_count": len(raw_pages),
                "block_count": len(all_blocks),
                "chunk_count": len(chunks),
                "status": "READY",
            }
        except Exception:
            self.sources.update(source_id, status="FAILED")
            raise

    def _load_pages(self, path: Path, fmt: str) -> list[RawPage]:
        if fmt == "pdf":
            return extract_pages(path)
        if fmt in {"md", "txt", "markdown"}:
            return parse_text_file(path).pages
        if fmt == "docx":
            return parse_docx(path).pages
        if fmt == "pptx":
            return parse_pptx(path).pages
        if fmt in {"xlsx", "xlsm", "csv"}:
            return parse_spreadsheet(path).pages
        if fmt in {"hwp", "hwpx"}:
            return parse_hwp(path).pages
        raise ValueError(f"Unsupported format: {fmt}")

    def _insert_metric(self, row: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO metric_facts (
                metric_id, source_id, page_number, name, definition,
                measurement_method, baseline_value, result_value, change_value,
                change_unit, direction, confidence, verification_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["metric_id"],
                row["source_id"],
                row["page_number"],
                row["name"],
                row["definition"],
                row["measurement_method"],
                row["baseline_value"],
                row["result_value"],
                row["change_value"],
                row["change_unit"],
                row["direction"],
                row["confidence"],
                row["verification_status"],
                row["payload_json"],
            ),
        )
        self.conn.commit()

    def _clear_metrics(self, source_id: str) -> None:
        self.conn.execute("DELETE FROM metric_facts WHERE source_id = ?", (source_id,))
        self.conn.commit()

    def _clear_structure(self, source_id: str) -> None:
        self.conn.execute(
            "DELETE FROM structure_facts WHERE source_id = ?", (source_id,)
        )
        self.conn.commit()

    def _insert_structure(self, row: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO structure_facts (
                fact_id, source_id, page_number, fact_kind, title,
                payload_json, confidence, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["fact_id"],
                row["source_id"],
                row["page_number"],
                row["fact_kind"],
                row["title"],
                row["payload_json"],
                row["confidence"],
                row["verification_status"],
            ),
        )
        self.conn.commit()


def _norm_key(text: str) -> str:
    # strip spaces/punct so "기존대비8%" == "기존 대비 8%"
    return re.sub(r"[^0-9a-z가-힣%+\-]", "", (text or "").lower())


def _is_duplicate_of_existing(text: str, existing_keys: list[str]) -> bool:
    key = _norm_key(text)
    if not key or len(key) < 2:
        return True
    for ek in existing_keys:
        if not ek:
            continue
        if key == ek:
            return True
        # containment for OCR vs concatenated PDF text
        shorter, longer = (key, ek) if len(key) <= len(ek) else (ek, key)
        if len(shorter) >= 4 and shorter in longer:
            return True
        # high character overlap
        if len(shorter) >= 6:
            overlap = sum(1 for ch in set(shorter) if ch in longer)
            if overlap / max(len(set(shorter)), 1) >= 0.85 and abs(len(key) - len(ek)) <= 8:
                return True
    return False


def _page_text_from_blocks(blocks: list) -> str:
    lines = []
    seen: set[str] = set()
    for b in blocks:
        if getattr(b, "block_type", "") == "IMAGE":
            continue
        t = (getattr(b, "text", None) or "").strip()
        if not t or t == "[IMAGE]":
            continue
        # section markers keep leading § for readability
        k = _norm_key(t)
        if k in seen:
            continue
        seen.add(k)
        lines.append(t)
    return "\n".join(lines)


def _should_extract_structure(layout, raw: RawPage) -> bool:
    """Only run graph extract on diagram-like pages (not every title slide)."""
    if layout.page_type not in {PageType.DIAGRAM, PageType.MIXED, PageType.CHART}:
        return False
    blocks = [
        b
        for b in layout.blocks
        if b.block_type in {"TEXT", "OCR"} and (b.text or "").strip()
    ]
    if len(blocks) < 5:
        return False
    table_n = sum(1 for b in layout.blocks if b.block_type == "TABLE")
    if table_n >= 5:
        return False
    short = 0
    for b in blocks:
        head = (b.text or "").splitlines()[0].strip()
        if 1 < len(head) <= 22 and "|" not in head:
            short += 1
    drawings = getattr(raw, "drawings", None) or []
    line_n = sum(1 for d in drawings if d.kind == "line")
    if line_n >= 6:
        return True
    if short >= 10:
        return True
    if layout.page_type == PageType.DIAGRAM and short >= 6 and line_n >= 2:
        return True
    if layout.page_type == PageType.MIXED and short >= 12:
        return True
    return False
