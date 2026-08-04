"""ADK workflow runner entrypoint.

Planning/production orchestration will be migrated to this runner in phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.adk_app.model_factory import build_litellm_model
from backend.adk_app.workflows.planning_workflow import run_corpus_analysis


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
        if config.workflow_name == "planning_workflow.corpus_analysis":
            analysis = run_corpus_analysis(
                (config.payload or {}).get("context") or {},
                mode=((config.payload or {}).get("mode") or "adk"),
            )
            return {
                "workflow_name": config.workflow_name,
                "project_id": config.project_id,
                "edition_id": config.edition_id,
                "status": "COMPLETED",
                "output": analysis.model_dump(),
            }

        # Placeholder envelope for remaining phase workflows.
        return {
            "workflow_name": config.workflow_name,
            "project_id": config.project_id,
            "edition_id": config.edition_id,
            "status": "PLANNED",
        }
