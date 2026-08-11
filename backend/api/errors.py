"""Thin API error helpers — no new error framework."""

from __future__ import annotations

from fastapi import HTTPException

from backend.model_providers.base import LlmError


def http_from_llm_error(exc: LlmError, *, role: str) -> HTTPException:
    """Map upstream LLM failure to a safe client-visible HTTP error.

    Frontend displays response body text as-is (contract freeze). Do not include
    stack traces, secrets, full prompts, or source content.
    """
    reason = _safe_llm_reason(exc)
    return HTTPException(
        status_code=502,
        detail=f"{role} model request failed: {reason}",
    )


def _safe_llm_reason(exc: LlmError) -> str:
    text = str(exc or "").strip() or "unknown upstream model error"
    # Drop accidental multiline / traceback-looking tails
    first = text.splitlines()[0].strip()
    # Avoid leaking long model echo / prompt fragments
    if len(first) > 400:
        first = first[:400] + "…"
    lower = first.lower()
    for needle in ("password", "authorization", "api_key", "secret", "token="):
        if needle in lower:
            return "upstream model request failed"
    return first
