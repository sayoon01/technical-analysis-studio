"""Mermaid process-flow specs + PNG fallback (no mermaid CLI required)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def to_mermaid_flowchart(steps: list[str], *, title: str | None = None) -> str:
    lines = ["flowchart LR"]
    if title:
        lines.append(f"  %% {title}")
    ids = []
    for i, step in enumerate(steps):
        nid = f"S{i}"
        ids.append(nid)
        safe = step.replace('"', "'")
        lines.append(f'  {nid}["{safe}"]')
    for a, b in zip(ids, ids[1:], strict=False):
        lines.append(f"  {a} --> {b}")
    return "\n".join(lines) + "\n"


def write_mermaid(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def render_process_png(
    path: Path,
    steps: list[str],
    *,
    title: str = "프로세스 흐름",
    source_note: str | None = None,
) -> Path:
    from matplotlib import font_manager

    path.parent.mkdir(parents=True, exist_ok=True)
    if Path(FONT).exists():
        font_manager.fontManager.addfont(FONT)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(max(8, len(steps) * 1.8), 3.2))
    ax.set_xlim(0, max(len(steps), 1) * 2)
    ax.set_ylim(0, 3)
    ax.axis("off")
    ax.set_title(title)

    for i, step in enumerate(steps):
        x = 0.4 + i * 2
        box = FancyBboxPatch(
            (x, 1.1),
            1.4,
            0.8,
            boxstyle="round,pad=0.05",
            linewidth=1.2,
            edgecolor="#1d3557",
            facecolor="#a8dadc",
        )
        ax.add_patch(box)
        ax.text(x + 0.7, 1.5, step, ha="center", va="center", fontsize=9)
        if i < len(steps) - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + 1.45, 1.5),
                    (x + 1.95, 1.5),
                    arrowstyle="->",
                    mutation_scale=12,
                    color="#1d3557",
                )
            )
    if source_note:
        fig.text(0.01, 0.02, source_note, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
