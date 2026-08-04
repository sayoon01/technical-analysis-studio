"""ADK workflow runner entrypoint.

Planning/production orchestration will be migrated to this runner in phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.adk_app.model_factory import build_litellm_model


@dataclass(slots=True)
class AdkRunConfig:
    workflow_name: str
    project_id: str
    edition_id: str | None = None
    payload: dict[str, Any] | None = None


class AdkRunner:
    """Minimal ADK runner scaffold used by migration smoke tests."""

    def build_model(self, model_id: str | None = None):
        return build_litellm_model(model_id=model_id)

    def run(self, config: AdkRunConfig) -> dict[str, Any]:
        # Placeholder envelope for phase-3; real graph execution follows.
        return {
            "workflow_name": config.workflow_name,
            "project_id": config.project_id,
            "edition_id": config.edition_id,
            "status": "PLANNED",
        }
