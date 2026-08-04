"""Prompt loader for ADK agents."""

from __future__ import annotations

from pathlib import Path


def load_prompt(relative_path: str) -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / relative_path
    return path.read_text(encoding="utf-8")
