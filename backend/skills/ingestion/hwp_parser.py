"""HWP / HWPX ingestion — text extraction only (domain-agnostic)."""

from __future__ import annotations

import re
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

from backend.skills.ingestion.pdf_parser import RawPage, RawTextBlock
from backend.skills.ingestion.text_parser import TextDocument, _split_by_size


def parse_hwp(path: str | Path) -> TextDocument:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".hwpx":
        text = _extract_hwpx_text(path)
    elif ext == ".hwp":
        text = _extract_hwp_text(path)
    else:
        raise ValueError(f"Not an HWP family file: {ext}")
    text = _normalize_ws(text)
    if not text.strip():
        raise ValueError(f"No extractable text in {path.name}")
    return _to_document(text)


def _to_document(full: str) -> TextDocument:
    chunks = _split_by_size(full, 3000)
    pages: list[RawPage] = []
    for i, chunk in enumerate(chunks, start=1):
        block = RawTextBlock(
            text=chunk,
            bbox=(0.0, 0.0, 612.0, 792.0),
            block_type="TEXT",
            confidence=0.85,
        )
        pages.append(
            RawPage(
                page_number=i,
                width=612.0,
                height=792.0,
                text_layer_available=True,
                full_text=chunk,
                blocks=[block],
            )
        )
    return TextDocument(pages=pages)


def _extract_hwpx_text(path: Path) -> str:
    """HWPX is a ZIP of XML sections — collect all text nodes."""
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            n
            for n in zf.namelist()
            if "/section" in n.lower() and n.lower().endswith(".xml")
        )
        if not names:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        for name in names:
            raw = zf.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            for el in root.iter():
                if el.text and el.text.strip():
                    parts.append(el.text.strip())
                if el.tail and el.tail.strip():
                    parts.append(el.tail.strip())
    return "\n".join(parts)


def _extract_hwp_text(path: Path) -> str:
    """Classic HWP (OLE): prefer PrvText, else inflate BodyText streams."""
    try:
        import olefile
    except ImportError as e:
        raise RuntimeError(
            "olefile is required for .hwp ingestion. pip install olefile"
        ) from e

    if not olefile.isOleFile(str(path)):
        raise ValueError(f"Not a valid OLE HWP file: {path.name}")

    with olefile.OleFileIO(str(path)) as ole:
        if ole.exists("PrvText"):
            data = ole.openstream("PrvText").read()
            text = data.decode("utf-16-le", errors="ignore").strip("\x00").strip()
            if text:
                return text

        # BodyText/SectionN — records are zlib-compressed in many HWP5 files
        sections = sorted(
            e for e in ole.listdir() if e and e[0] == "BodyText" and len(e) >= 2
        )
        chunks: list[str] = []
        for entry in sections:
            try:
                raw = ole.openstream(entry).read()
            except OSError:
                continue
            chunks.append(_decode_hwp_body(raw))
        return "\n".join(c for c in chunks if c)


def _decode_hwp_body(data: bytes) -> str:
    """Best-effort: try zlib slices then utf-16 / cp949 printable runs."""
    texts: list[str] = []
    # Try whole-stream inflate
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            inflated = zlib.decompress(data, wbits)
            t = _bytes_to_text(inflated)
            if t:
                return t
        except zlib.error:
            pass
    # Scan for embedded zlib streams
    for i in range(len(data) - 2):
        if data[i] == 0x78 and data[i + 1] in (0x01, 0x9C, 0xDA):
            try:
                inflated = zlib.decompress(data[i:])
            except zlib.error:
                continue
            t = _bytes_to_text(inflated)
            if len(t) > 20:
                texts.append(t)
    if texts:
        return "\n".join(texts)
    return _bytes_to_text(data)


def _bytes_to_text(data: bytes) -> str:
    for enc in ("utf-16-le", "cp949", "utf-8"):
        try:
            s = data.decode(enc, errors="ignore")
        except LookupError:
            continue
        # Keep lines with Hangul / alnum density
        kept = []
        for ln in s.splitlines():
            ln = ln.strip("\x00").strip()
            if not ln:
                continue
            hangul = sum(1 for c in ln if "가" <= c <= "힣")
            alnum = sum(1 for c in ln if c.isalnum())
            if hangul >= 2 or alnum >= 6:
                kept.append(ln)
        if kept:
            return "\n".join(kept)
    return ""


def _normalize_ws(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
