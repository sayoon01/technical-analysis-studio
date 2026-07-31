"""Ollama chat client (JSON mode for structured agent outputs)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import settings
from backend.model_providers.registry import agent_model_config

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    pass


def resolve_ollama_model(agent_name: str | None = None) -> str:
    """Env `OLLAMA_MODEL`/`GEMMA_MODEL` wins; else models.yaml model_id; else settings."""
    if os.getenv("OLLAMA_MODEL") or os.getenv("GEMMA_MODEL"):
        return settings.ollama_model
    if agent_name:
        logical = agent_model_config(agent_name).get("model_id")
        if logical:
            return str(logical)
    return settings.ollama_model


def ollama_reachable(timeout: float = 5.0) -> tuple[bool, list[str]]:
    """Return (ok, model_names)."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models") or []]
        return True, [n for n in names if n]
    except httpx.HTTPError:
        return False, []


def call_ollama_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
    images_b64: list[str] | None = None,
) -> dict[str, Any]:
    chosen = model or settings.ollama_model
    user_msg: dict[str, Any] = {"role": "user", "content": user_prompt}
    if images_b64:
        user_msg["images"] = images_b64
    payload = {
        "model": chosen,
        "messages": [
            {"role": "system", "content": system_prompt},
            user_msg,
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_predict": 4096,
        },
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    wait = timeout if timeout is not None else settings.ollama_timeout
    try:
        resp = httpx.post(url, json=payload, timeout=wait)
        resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise LlmError(f"Ollama request timed out ({chosen}, {wait}s): {e}") from e
    except httpx.HTTPError as e:
        raise LlmError(f"Ollama request failed ({chosen}): {e}") from e

    content = resp.json().get("message", {}).get("content", "")
    return parse_json_object(content)


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise LlmError("Empty LLM response")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Extract fenced or first {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise LlmError(f"No JSON object in response: {text[:200]}")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise LlmError("JSON root is not an object")
    return data


def generate_structured(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    agent_name: str,
    max_retries: int = 2,
) -> T:
    cfg = agent_model_config(agent_name)
    model = resolve_ollama_model(agent_name)

    # Field names only — full JSON Schema bloats prompts and slows 31B models.
    fields = list(schema.model_json_schema().get("properties", {}).keys())
    schema_hint = (
        "Respond with a single JSON object using these keys only:\n"
        f"{json.dumps(fields, ensure_ascii=False)}\n"
        "Rules: list fields must be JSON arrays. "
        "quantitative_findings must be an array of objects "
        'like {"name":"...","change":"...","change_value":8,"change_unit":"%"} '
        "not plain strings."
    )
    sys = f"{system_prompt}\n\n{schema_hint}"
    last_err: Exception | None = None
    prompt = user_prompt
    for attempt in range(max_retries + 1):
        try:
            logger.info(
                "ollama generate agent=%s model=%s attempt=%s chars=%s",
                agent_name,
                model,
                attempt + 1,
                len(sys) + len(prompt),
            )
            raw = call_ollama_json(
                sys,
                prompt,
                model=model,
                temperature=float(cfg.get("temperature", 0.2)),
            )
            return schema.model_validate(raw)
        except (LlmError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            logger.warning(
                "ollama generate failed agent=%s attempt=%s err=%s",
                agent_name,
                attempt + 1,
                e,
            )
            # Timeouts are not fixed by retrying the same huge prompt.
            if "timed out" in str(e).lower():
                break
            prompt = (
                user_prompt
                + f"\n\nPrevious output failed validation: {e}\n"
                "Return corrected JSON only."
            )
    raise LlmError(f"Structured generation failed after retries: {last_err}")


def allow_offline_fallback() -> bool:
    """When TAS_LLM_MODE=llm, silent offline fallback is on unless TAS_LLM_STRICT=1."""
    if settings.llm_mode == "offline":
        return True
    return os.getenv("TAS_LLM_STRICT", "0").lower() not in ("1", "true", "yes")
