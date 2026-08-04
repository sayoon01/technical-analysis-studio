"""Google ADK model factory using LiteLlm + Ollama."""

from __future__ import annotations

from backend.config import settings


def build_litellm_model(model_id: str | None = None):
    """Create LiteLlm model with ollama_chat naming convention.

    Import is lazy so test/offline environments without google-adk installed
    can still import this module safely.
    """
    from google.adk.models.lite_llm import LiteLlm

    resolved = (model_id or settings.ollama_model).strip()
    if not resolved:
        raise ValueError("model_id is required")
    return LiteLlm(
        model=f"ollama_chat/{resolved}",
        api_base=settings.ollama_base_url,
    )
