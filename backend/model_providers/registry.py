"""YAML config loader for models / retrieval / etc."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@lru_cache(maxsize=16)
def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def agent_model_config(agent_name: str) -> dict[str, Any]:
    cfg = load_yaml("models.yaml")
    agents = cfg.get("agents") or {}
    models = cfg.get("models") or {}
    agent = agents.get(agent_name) or {}
    model_key = agent.get("model", "gemma-default")
    model = models.get(model_key) or {}
    return {
        "model_id": model.get("model_id"),
        "temperature": agent.get("temperature", 0.2),
        "max_tokens": model.get("max_tokens", 4096),
        "provider": model.get("provider", "gemma"),
    }
