"""Text embedder — Ollama (bge-m3 / 1024-d) with explicit hash-only offline mode.

Vector indexes must never mix hash(256) and model(1024) vectors.
"""

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

# Hash fallback dim (offline / TAS_EMBEDDING_MODE=hash only). Never write into
# an Ollama-backed index.
_HASH_DIM = 256
# Default index / search dim for bge-m3
_DEFAULT_INDEX_DIM = 1024

_cache_lock = threading.Lock()
_dim_cache: dict[str, int] = {}


class EmbeddingError(RuntimeError):
    """Raised when a required embedding cannot be produced at the index dimension."""


def embedding_model() -> str:
    return (
        os.getenv("EMBEDDING_MODEL")
        or os.getenv("OLLAMA_EMBED_MODEL")
        or settings.embedding_model
    )


def index_embed_dim() -> int:
    """Canonical dimension for vector indexes in Ollama/bge-m3 mode."""
    env = os.getenv("EMBEDDING_DIM")
    if env:
        return int(env)
    with _cache_lock:
        cached = _dim_cache.get(embedding_model())
    return int(cached or _DEFAULT_INDEX_DIM)


def use_ollama_embeddings() -> bool:
    if settings.llm_mode == "offline":
        return False
    mode = os.getenv("TAS_EMBEDDING_MODE", "ollama").lower()
    return mode not in ("hash", "offline", "local")


def embed_text(
    text: str,
    dim: int | None = None,
    *,
    strict: bool | None = None,
) -> list[float]:
    """Embed text.

    - Ollama mode (default): always returns ``index_embed_dim()`` vectors.
      Failures raise ``EmbeddingError`` (no silent hash fallback into indexes).
    - Hash/offline mode: deterministic ``_HASH_DIM`` (or ``dim``) vectors.
    """
    if strict is None:
        strict = use_ollama_embeddings()

    model = embedding_model()
    if use_ollama_embeddings():
        expected = dim or index_embed_dim()
        try:
            vec = _ollama_embed(text, model=model, expected_dim=expected)
            if len(vec) != expected:
                raise EmbeddingError(
                    f"embedding dim mismatch: got {len(vec)}, expected {expected} "
                    f"(model={model})"
                )
            return vec
        except EmbeddingError:
            raise
        except Exception as e:
            msg = f"ollama embedding failed ({model}): {e}"
            if strict:
                raise EmbeddingError(msg) from e
            logger.warning("%s; hash fallback disabled for index safety", msg)
            raise EmbeddingError(msg) from e

    return _hash_embed(text, dim or _HASH_DIM)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(a[i] * b[i] for i in range(len(a)))


def _ollama_embed(text: str, *, model: str, expected_dim: int) -> list[float]:
    prompt = (text or "").strip()
    if not prompt:
        return [0.0] * expected_dim
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    payload = {"model": model, "prompt": prompt[:8000]}
    timeout = min(60.0, float(settings.ollama_timeout))
    last_err: Exception | None = None
    for attempt in range(2):
        try:
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
        except Exception as e:
            last_err = e
            if attempt == 0:
                logger.warning("ollama embed retry after error: %s", e)
                continue
            raise
    raise RuntimeError(str(last_err))


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
