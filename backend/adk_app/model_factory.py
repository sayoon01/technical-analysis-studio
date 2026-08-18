"""Legacy shim for ADK model construction."""

from __future__ import annotations

from backend.adk_app.model_adapter import build_agent_model


def build_litellm_model(model_id: str | None = None):
    # model_id is ignored; agent role controls model selection.
    return build_agent_model("corpus_analyst")
