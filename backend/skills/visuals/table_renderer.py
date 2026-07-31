"""Markdown / HTML / CSV table rendering."""

from __future__ import annotations

import csv
from pathlib import Path


def render_markdown_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    title: str | None = None,
) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"**{title}**")
        lines.append("")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(str(c) for c in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return path
