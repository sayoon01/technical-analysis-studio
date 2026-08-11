"""Ollama chat client (JSON mode for structured agent outputs)."""

from __future__ import annotations

import hashlib
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
    max_tokens: int | None = None,
) -> dict[str, Any]:
    chosen = model or settings.ollama_model
    user_msg: dict[str, Any] = {"role": "user", "content": user_prompt}
    if images_b64:
        user_msg["images"] = images_b64
    predict = int(max_tokens) if max_tokens and int(max_tokens) > 0 else 4096
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
            "num_predict": predict,
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
    # provenance is agent-owned (online/offline), never requested from the LLM.
    fields = [
        k
        for k in schema.model_json_schema().get("properties", {}).keys()
        if k != "provenance"
    ]
    name = schema.__name__
    if name in {"CorpusAnalysis", "ReportPlan"}:
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Rules: list fields must be JSON arrays. "
            "quantitative_findings must be an array of objects "
            'like {"name":"...","change":"...","change_value":8,"change_unit":"%"} '
            "not plain strings."
        )
    elif name == "EvidenceRefineDelta":
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Use existing candidate ids only. Do not invent ids or rewrite evidence bodies. "
            "keep_ids/drop_ids/ranking are string arrays; conflicts is an array of "
            '{"description":"...","evidence_ids":["…"]}.'
        )
    elif name == "ChapterDraft":
        schema_hint = (
            "Respond with a single JSON object matching ChapterDraft keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "subsections is an array of {subsection_id,title,paragraphs[]} where "
            "paragraphs items are {paragraph_id,paragraph_type,text,evidence_ids[]}. "
            "paragraph_type must be FACT|SYNTHESIS|ANALYSIS|LIMITATION. "
            "Do not wrap the object under chapter_draft/draft. "
            "Do not invent evidence_ids absent from the provided Evidence Pack."
        )
    elif name == "TechnicalReview":
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Rules: decision is PASS|REVISE|MANUAL_REVIEW; "
            "issues MUST be a JSON array of objects (never plain strings), each with "
            "{issue_id,section_id,reviewer_type,severity,issue_type,"
            "description,recommendation,status}; "
            "severity is CRITICAL|MAJOR|MINOR; "
            "evidence_coverage is a float between 0 and 1 (not a percent string); "
            "unsupported_claim_count, citation_mismatch_count, numeric_mismatch_count, "
            "critical_issue_count are integers. Do not include provenance."
        )
    elif name == "EditorialReview":
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Rules: decision is PASS|REVISE|MANUAL_REVIEW; "
            "issues MUST be a JSON array of objects (never plain strings), each with "
            "{issue_id,section_id,reviewer_type,severity,issue_type,"
            "description,recommendation,status}; "
            "severity is CRITICAL|MAJOR|MINOR; "
            "duplicate_paragraph_ratio is a float 0-1; counts are integers. "
            "Do not include provenance."
        )
    elif name == "RevisionResult":
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Rules: revision is an integer; updated_content is the full revised "
            "markdown string; changes MUST be a JSON array of objects (never plain "
            "strings), each like {change_type,reason,issue_id?}; "
            "resolved_issue_ids is a JSON array of issue_id strings. "
            "Do not include provenance."
        )
    else:
        schema_hint = (
            "Respond with a single JSON object using these keys only:\n"
            f"{json.dumps(fields, ensure_ascii=False)}\n"
            "Rules: list fields must be JSON arrays; do not invent required id fields."
        )
    sys = f"{system_prompt}\n\n{schema_hint}"
    last_err: Exception | None = None
    prompt = user_prompt
    max_tokens = int(cfg.get("max_tokens") or 4096)
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
                max_tokens=max_tokens,
            )
            if name == "ChapterDraft" and isinstance(raw, dict):
                # Tolerate legacy wrapped payloads without a second gateway.
                if isinstance(raw.get("chapter_draft"), dict):
                    raw = raw["chapter_draft"]
                elif isinstance(raw.get("draft"), dict):
                    raw = raw["draft"]
            if name == "RevisionResult" and isinstance(raw, dict):
                if isinstance(raw.get("revision_result"), dict):
                    raw = raw["revision_result"]
                elif isinstance(raw.get("result"), dict) and (
                    "updated_content" in raw["result"] or "changes" in raw["result"]
                ):
                    raw = raw["result"]
            if isinstance(raw, dict):
                raw = _normalize_structured_raw(name, raw)
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


def _normalize_structured_raw(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce common LLM quirks before Pydantic validation (single schema kept)."""
    data = dict(raw)
    # provenance is set by the agent after a successful call
    data.pop("provenance", None)

    reviewer_type = (
        "technical"
        if name == "TechnicalReview"
        else "editorial"
        if name == "EditorialReview"
        else "unknown"
    )
    section_hint = _first_str(
        data.get("section_id"),
        data.get("chapter_id"),
    )

    if name == "TechnicalReview":
        ec = data.get("evidence_coverage")
        if isinstance(ec, str):
            cleaned = ec.strip().replace("%", "").replace(",", ".")
            try:
                val = float(cleaned)
                # "100%" / "85" → ratio when clearly a percent
                if val > 1.0:
                    val = val / 100.0
                data["evidence_coverage"] = val
            except ValueError:
                data.pop("evidence_coverage", None)
        for key in (
            "unsupported_claim_count",
            "citation_mismatch_count",
            "numeric_mismatch_count",
            "critical_issue_count",
        ):
            if key in data:
                data[key] = _coerce_int(data[key], default=0)
        if isinstance(data.get("issues"), list):
            data["issues"] = [
                _normalize_issue_dict(
                    i,
                    reviewer_type=reviewer_type,
                    section_id=section_hint,
                    index=idx,
                )
                for idx, i in enumerate(data["issues"])
            ]

    if name == "EditorialReview":
        ratio = data.get("duplicate_paragraph_ratio")
        if isinstance(ratio, str):
            cleaned = ratio.strip().replace("%", "").replace(",", ".")
            try:
                val = float(cleaned)
                if val > 1.0:
                    val = val / 100.0
                data["duplicate_paragraph_ratio"] = val
            except ValueError:
                data.pop("duplicate_paragraph_ratio", None)
        for key in (
            "promotional_phrase_count",
            "terminology_inconsistency_count",
            "critical_issue_count",
        ):
            if key in data:
                data[key] = _coerce_int(data[key], default=0)
        if isinstance(data.get("issues"), list):
            data["issues"] = [
                _normalize_issue_dict(
                    i,
                    reviewer_type=reviewer_type,
                    section_id=section_hint,
                    index=idx,
                )
                for idx, i in enumerate(data["issues"])
            ]

    if name == "RevisionResult":
        # Alias content fields without inventing body text.
        if not _first_str(data.get("updated_content")):
            alt = _first_str(
                data.get("content"),
                data.get("markdown"),
                data.get("revised_content"),
                data.get("updated_markdown"),
            )
            if alt:
                data["updated_content"] = alt
        if "revision" in data:
            data["revision"] = _coerce_int(data["revision"], default=1)
        if isinstance(data.get("changes"), list):
            data["changes"] = [
                _normalize_change_item(item, index=idx)
                for idx, item in enumerate(data["changes"])
            ]
        elif data.get("changes") is None:
            data["changes"] = []
        else:
            # Single string / unexpected scalar → one change object
            data["changes"] = [_normalize_change_item(data["changes"], index=0)]
        data["resolved_issue_ids"] = _normalize_id_list(
            data.get("resolved_issue_ids")
        )

    return data


def _normalize_change_item(item: Any, *, index: int = 0) -> dict[str, Any]:
    """Coerce LLM change quirks (plain strings) into offline-compatible dicts."""
    if isinstance(item, dict):
        out = dict(item)
        # Ensure at least one human-readable field exists for downstream logs/UI.
        if not _first_str(
            out.get("reason"),
            out.get("description"),
            out.get("summary"),
            out.get("message"),
        ):
            out["reason"] = f"change {index + 1}"
        out["change_type"] = (
            _first_str(out.get("change_type"), out.get("type")) or "NOTE"
        )
        return out
    if isinstance(item, str):
        text = item.strip().lstrip("-•* ").strip() or f"change {index + 1}"
        return {"change_type": "NOTE", "reason": text}
    return {"change_type": "NOTE", "reason": str(item)}


def _normalize_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            iid = _first_str(item.get("issue_id"), item.get("id"))
            if iid:
                out.append(iid)
    return out


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        try:
            return int(float(cleaned))
        except ValueError:
            return default
    return default


def _first_str(*values: Any) -> str | None:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


_SEVERITY_ALIASES = {
    "CRIT": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "MAJOR": "MAJOR",
    "HIGH": "MAJOR",
    "MINOR": "MINOR",
    "LOW": "MINOR",
    "INFO": "MINOR",
    "INFORMATIONAL": "MINOR",
    "WARNING": "MINOR",
}
_VALID_SEVERITIES = frozenset({"CRITICAL", "MAJOR", "MINOR"})


def _issue_id_is_garbage(iid: str) -> bool:
    s = iid.strip()
    if not s:
        return True
    if "/" in s or "\n" in s or s.startswith("//"):
        return True
    if len(s) > 64:
        return True
    return False


def _normalize_issue_dict(
    item: Any,
    *,
    reviewer_type: str,
    section_id: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    """Coerce LLM issue quirks (plain strings / partial objects) into ReviewIssue shape."""
    if isinstance(item, str):
        text = item.strip()
        out: dict[str, Any] = {
            "description": text or f"Issue {index + 1}",
            "issue_type": "GENERAL",
        }
    elif isinstance(item, dict):
        out = dict(item)
    else:
        out = {"description": str(item), "issue_type": "GENERAL"}

    desc = _first_str(
        out.get("description"),
        out.get("problem"),
        out.get("message"),
        out.get("text"),
        out.get("summary"),
    )
    if not desc:
        desc = f"Issue {index + 1}"
    out["description"] = desc

    rec = _first_str(
        out.get("recommendation"),
        out.get("required_change"),
        out.get("fix"),
        out.get("suggestion"),
        out.get("action"),
    )
    if not rec:
        rec = "Address the described issue in the section draft."
    out["recommendation"] = rec

    itype = _first_str(out.get("issue_type"), out.get("category"), out.get("type"))
    out["issue_type"] = (itype or "GENERAL").strip().upper().replace(" ", "_")[:64]

    iid = _first_str(out.get("issue_id"), out.get("id"))
    if not iid or _issue_id_is_garbage(iid):
        digest = hashlib.sha1(
            f"{reviewer_type}:{index}:{desc}".encode()
        ).hexdigest()[:10].upper()
        iid = f"ISS-{digest}"
    elif not iid.upper().startswith("ISS"):
        digest = hashlib.sha1(iid.encode()).hexdigest()[:8].upper()
        iid = f"ISS-{digest}"
    out["issue_id"] = iid

    sid = _first_str(out.get("section_id"), section_id) or "UNKNOWN"
    out["section_id"] = sid

    rtype = _first_str(out.get("reviewer_type"), reviewer_type) or "unknown"
    out["reviewer_type"] = rtype.strip().lower()

    sev_raw = out.get("severity")
    if isinstance(sev_raw, str):
        key = sev_raw.strip().upper()
        mapped = _SEVERITY_ALIASES.get(key, key)
        out["severity"] = mapped if mapped in _VALID_SEVERITIES else "MAJOR"
    else:
        out["severity"] = "MAJOR"

    if out.get("status") is None or not isinstance(out.get("status"), str):
        out["status"] = "OPEN"
    else:
        out["status"] = out["status"].strip().upper() or "OPEN"

    refs = out.get("evidence_refs")
    if refs is None:
        out["evidence_refs"] = []
    elif isinstance(refs, str):
        out["evidence_refs"] = [refs] if refs.strip() else []
    elif not isinstance(refs, list):
        out["evidence_refs"] = []

    return out


def allow_offline_fallback() -> bool:
    """When TAS_LLM_MODE=llm, silent offline fallback is on unless TAS_LLM_STRICT=1."""
    if settings.llm_mode == "offline":
        return True
    return os.getenv("TAS_LLM_STRICT", "0").lower() not in ("1", "true", "yes")
