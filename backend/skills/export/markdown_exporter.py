"""Markdown exporter."""

from __future__ import annotations

from pathlib import Path


def export_markdown(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
