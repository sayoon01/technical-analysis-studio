"""Detect supported upload formats (PDF/DOCX/MD/TXT + PPTX/XLSX/CSV/HWP)."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".md",
    ".txt",
    ".markdown",
    ".pptx",
    ".xlsx",
    ".xlsm",
    ".csv",
    ".hwp",
    ".hwpx",
}
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
    ".hwp": "application/x-hwp",
    ".hwpx": "application/hwp+zip",
}


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: {ext or '(none)'}")
    return ext.lstrip(".")


def guess_mime(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return MIME_BY_EXT.get(ext, "application/octet-stream")


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


# Back-compat alias
MVP_EXTENSIONS = SUPPORTED_EXTENSIONS
