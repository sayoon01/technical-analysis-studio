"""matplotlib chart renderer."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def _setup_font() -> None:
    from matplotlib import font_manager

    if Path(FONT).exists():
        font_manager.fontManager.addfont(FONT)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams["axes.unicode_minus"] = False


def render_bar_chart(
    path: Path,
    *,
    title: str,
    labels: list[str],
    values: list[float],
    ylabel: str = "변화(%)",
    source_note: str | None = None,
) -> Path:
    _setup_font()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#2a9d8f" if v >= 0 else "#e76f51" for v in values]
    ax.bar(labels, values, color=colors)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.axhline(0, color="#666", linewidth=0.8)
    if source_note:
        fig.text(0.01, 0.01, source_note, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def render_line_chart(
    path: Path,
    *,
    title: str,
    labels: list[str],
    values: list[float],
    ylabel: str = "값",
    source_note: str | None = None,
) -> Path:
    _setup_font()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(labels, values, marker="o", color="#457b9d")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if source_note:
        fig.text(0.01, 0.01, source_note, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
