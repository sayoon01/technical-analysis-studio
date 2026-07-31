"""Architecture diagram: Graphviz DOT text + PNG fallback."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def to_dot(
    nodes: list[dict],
    edges: list[dict],
    *,
    title: str | None = None,
) -> str:
    """nodes: [{id,label}], edges: [{from,to,label?}]"""
    lines = ["digraph G {", "  rankdir=LR;", '  node [shape=box, style=rounded];']
    if title:
        lines.append(f'  labelloc="t"; label="{title}";')
    for n in nodes:
        nid = str(n.get("id") or n.get("label"))
        label = str(n.get("label") or nid).replace('"', "'")
        lines.append(f'  "{nid}" [label="{label}"];')
    for e in edges:
        frm = e.get("from") or e.get("from_node_id")
        to = e.get("to") or e.get("to_node_id")
        label = e.get("label")
        if label:
            lines.append(f'  "{frm}" -> "{to}" [label="{label}"];')
        else:
            lines.append(f'  "{frm}" -> "{to}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def render_architecture_png(
    path: Path,
    nodes: list[dict],
    edges: list[dict],
    *,
    title: str = "시스템 구성",
    source_note: str | None = None,
) -> Path:
    from matplotlib import font_manager

    path.parent.mkdir(parents=True, exist_ok=True)
    if Path(FONT).exists():
        font_manager.fontManager.addfont(FONT)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams["axes.unicode_minus"] = False

    n = max(len(nodes), 1)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, ax = plt.subplots(figsize=(10, max(3.5, rows * 2.2)))
    ax.set_xlim(0, cols * 3.5)
    ax.set_ylim(0, rows * 2.5)
    ax.axis("off")
    ax.set_title(title)

    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(nodes):
        r, c = divmod(i, cols)
        x = 0.5 + c * 3.5
        y = (rows - r - 1) * 2.5 + 0.8
        nid = str(node.get("id") or node.get("label") or i)
        label = str(node.get("label") or nid)
        positions[nid] = (x + 1.2, y + 0.4)
        box = FancyBboxPatch(
            (x, y),
            2.4,
            0.9,
            boxstyle="round,pad=0.05",
            linewidth=1.4,
            edgecolor="#1d3557",
            facecolor="#f1faee",
        )
        ax.add_patch(box)
        ax.text(x + 1.2, y + 0.45, label, ha="center", va="center", fontsize=9)

    for e in edges:
        frm = str(e.get("from") or e.get("from_node_id"))
        to = str(e.get("to") or e.get("to_node_id"))
        if frm in positions and to in positions:
            ax.add_patch(
                FancyArrowPatch(
                    positions[frm],
                    positions[to],
                    arrowstyle="->",
                    mutation_scale=12,
                    color="#457b9d",
                    connectionstyle="arc3,rad=0.1",
                )
            )

    if source_note:
        fig.text(0.01, 0.02, source_note, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
