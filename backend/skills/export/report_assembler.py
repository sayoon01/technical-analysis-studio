"""Assemble final report markdown from sections + visual embeds."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.domain.publication import PublicationDocument


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


def publication_to_markdown(doc: PublicationDocument) -> str:
    lines: list[str] = [f"# {doc.title}", ""]
    if doc.subtitle:
        lines.append(f"*{doc.subtitle}*")
        lines.append("")

    lines.append("## 요약")
    lines.append("")
    lines.append(doc.executive_summary.overview)
    lines.append("")
    for h in doc.executive_summary.highlights:
        lines.append(f"- {h}")
    lines.append("")

    lines.append("## 본문")
    lines.append("")
    for ch in doc.chapters:
        lines.append(f"## {ch.title}")
        lines.append("")
        if ch.body_markdown:
            lines.append(ch.body_markdown)
            lines.append("")

    if doc.figures:
        lines.append("## 시각자료")
        lines.append("")
        for f in doc.figures:
            if f.asset_path:
                p = Path(f.asset_path)
                lines.append(f"![{f.title}](visuals/{p.name})")
            else:
                lines.append(f"### {f.title}")
            if f.caption:
                lines.append(f"*{f.caption}*")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def markdown_to_html(markdown: str, *, title: str) -> str:
    """Minimal deterministic renderer for export HTML artifact."""
    esc = (
        markdown.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    html_body = []
    for line in esc.split("\n"):
        if not line.strip():
            html_body.append("<p></p>")
            continue
        if line.startswith("# "):
            html_body.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("## "):
            html_body.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("- "):
            html_body.append(f"<li>{line[2:].strip()}</li>")
        elif line.startswith("![") and "](" in line and line.endswith(")"):
            alt = line[2:].split("](", 1)[0]
            src = line.split("](", 1)[1][:-1]
            html_body.append(f'<img alt="{alt}" src="{src}" style="max-width:100%;" />')
        else:
            html_body.append(f"<p>{line}</p>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        f"<title>{title}</title>"
        "<style>body{font-family:Arial,NanumGothic,sans-serif;line-height:1.65;max-width:920px;margin:32px auto;padding:0 16px;}h1,h2{margin-top:28px;}img{display:block;margin:12px 0;}li{margin-left:20px;}</style>"
        "</head><body>"
        + "\n".join(html_body)
        + "</body></html>"
    )
