"""Assemble final report markdown from sections + visual embeds."""

from __future__ import annotations

import json
import re
from pathlib import Path


def assemble_report_markdown(
    *,
    title: str,
    subtitle: str | None,
    sections: list[dict],
    visual_embeds: dict[str, str] | None = None,
    section_visuals: dict[str, list[str]] | None = None,
) -> str:
    """section_visuals: section_id -> [visual_id,...]"""
    lines = [f"# {title}", ""]
    if subtitle:
        lines.append(f"*{subtitle}*")
        lines.append("")

    lines.append("## 목차")
    lines.append("")
    for i, s in enumerate(sections, start=1):
        lines.append(f"{i}. {s.get('title')}")
    lines.append("")

    for s in sections:
        body = (s.get("content_markdown") or "").strip()
        # Drop duplicate top heading if assembler will rely on section title
        lines.append(body)
        lines.append("")
        vids = (section_visuals or {}).get(s["section_id"], [])
        for vid in vids:
            embed = (visual_embeds or {}).get(vid)
            if embed:
                lines.append(embed)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def number_figures(markdown: str) -> str:
    idx = 0

    def repl(m: re.Match) -> str:
        nonlocal idx
        idx += 1
        alt = m.group(1)
        path = m.group(2)
        return f"![그림 {idx}. {alt}]({path})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)
