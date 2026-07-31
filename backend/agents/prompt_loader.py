"""Load agent instructions from prompts/ — never hardcode long strings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"


@lru_cache(maxsize=64)
def load(relative_path: str) -> str:
    """e.g. load('technical_analysis/technical_writer.md')"""
    path = PROMPTS_DIR / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def load_agent_instruction(agent_name: str) -> str:
    common = load("technical_analysis/common.md")
    specific = load(f"technical_analysis/{agent_name}.md")
    return f"{common}\n\n---\n\n{specific}"
