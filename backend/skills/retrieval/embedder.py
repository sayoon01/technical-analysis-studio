"""Text embedder — Ollama embeddings with deterministic hash fallback."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_DIM = 256
_cache_lock = threading.Lock()
_dim_cache: dict[str, int] = {}


def embedding_model() -> str:
    return (
        os.getenv("EMBEDDING_MODEL")
        or os.getenv("OLLAMA_EMBED_MODEL")
        or settings.embedding_model
    )


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """Embed text via Ollama when available; otherwise hashing fallback.

    Callers must not assume a fixed dimension — use len(embed_text(...)).
    """
    model = embedding_model()
    use_ollama = settings.llm_mode != "offline" and os.getenv(
        "TAS_EMBEDDING_MODE", "ollama"
    ).lower() not in ("hash", "offline", "local")
    if use_ollama:
        try:
            vec = _ollama_embed(text, model=model)
            if dim is not None and len(vec) != dim:
                # Rare: caller asked for legacy dim — pad/truncate after normalize
                return _fit_dim(vec, dim)
            return vec
        except Exception as e:
            logger.warning("ollama embedding failed (%s); using hash fallback: %s", model, e)
    return _hash_embed(text, dim or _FALLBACK_DIM)


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(a[i] * b[i] for i in range(n))


def _ollama_embed(text: str, *, model: str) -> list[float]:
    prompt = (text or "").strip()
    if not prompt:
        # Match model dim if known
        d = _dim_cache.get(model, _FALLBACK_DIM)
        return [0.0] * d
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    # Keep payloads bounded for throughput
    payload = {"model": model, "prompt": prompt[:8000]}
    timeout = min(60.0, float(settings.ollama_timeout))
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    vec = data.get("embedding")
    if not isinstance(vec, list) or not vec:
        raise RuntimeError("empty embedding")
    out = [float(x) for x in vec]
    with _cache_lock:
        _dim_cache[model] = len(out)
    return _l2_normalize(out)


def _hash_embed(text: str, dim: int) -> list[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * dim
    vec = [0.0] * dim
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    return _l2_normalize(vec)


def _fit_dim(vec: list[float], dim: int) -> list[float]:
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return _l2_normalize(vec[:dim])
    return _l2_normalize(vec + [0.0] * (dim - len(vec)))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]{2,}")


def _tokenize(text: str) -> list[str]:
    base = [t.lower() for t in _TOKEN_RE.findall(text)]
    extras: list[str] = []
    compact = re.sub(r"\s+", "", text)
    for i in range(len(compact) - 1):
        extras.append(compact[i : i + 2])
    return base + extras[:200]
