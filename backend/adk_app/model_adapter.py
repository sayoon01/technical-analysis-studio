"""ADK model adapter for Phase 1 analyze workflow."""

from __future__ import annotations

from dataclasses import dataclass

from google.adk.models.lite_llm import LiteLLMClient, LiteLlm
from litellm import acompletion

from backend.config import settings
from backend.model_providers.registry import agent_model_config


@dataclass(frozen=True)
class ModelRoute:
    model_name: str
    timeout_seconds: float


class ConfiguredLiteLLMClient(LiteLLMClient):
    """Single gateway client: one Ollama-compatible base URL."""

    def __init__(self, *, api_base: str, timeout_seconds: float) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def acompletion(self, model, messages, tools, **kwargs):
        return await acompletion(
            model=model,
            messages=messages,
            tools=tools,
            api_base=self.api_base,
            timeout=self.timeout_seconds,
            **kwargs,
        )


def resolve_model_route(agent_name: str) -> ModelRoute:
    cfg = agent_model_config(agent_name)
    model_name = str(cfg.get("model_id") or settings.ollama_model).strip()
    return ModelRoute(
        model_name=model_name,
        timeout_seconds=float(settings.ollama_timeout),
    )


def build_agent_model(agent_name: str) -> LiteLlm:
    route = resolve_model_route(agent_name)
    client = ConfiguredLiteLLMClient(
        api_base=settings.ollama_base_url,
        timeout_seconds=route.timeout_seconds,
    )
    return LiteLlm(model=f"ollama_chat/{route.model_name}", llm_client=client)
