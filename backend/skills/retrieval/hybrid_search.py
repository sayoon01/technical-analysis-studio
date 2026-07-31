"""Hybrid retrieval: FTS ∪ vector → merge → dedupe."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from backend.skills.retrieval.embedder import EmbeddingError
from backend.skills.retrieval.keyword_search import keyword_search
from backend.skills.retrieval.vector_search import VectorStore

logger = logging.getLogger(__name__)


def hybrid_search(
    conn: sqlite3.Connection,
    project_id: str,
    query: str,
    *,
    source_ids: list[str] | None = None,
    keyword_top_k: int = 20,
    vector_top_k: int = 20,
    merged_top_k: int = 24,
    vector_root: Path | None = None,
) -> list[dict]:
    kw = keyword_search(conn, query, source_ids=source_ids, top_k=keyword_top_k)
    vec: list[dict] = []
    try:
        store = VectorStore(project_id, root=vector_root)
        vec = store.search(query, top_k=vector_top_k, source_ids=source_ids)
    except EmbeddingError as e:
        # Do not abort produce/resume when Ollama embeddings are temporarily down.
        logger.warning(
            "vector search skipped for %s (FTS-only): %s", project_id, e
        )

    merged: dict[str, dict] = {}
    # Prefer block_id from FTS; vector uses chunk_id — map by page+text head
    for i, row in enumerate(kw):
        key = row.get("block_id") or f"kw-{i}"
        item = dict(row)
        item["retrieval"] = "keyword"
        item["rank_score"] = 1.0 - (i * 0.01)
        merged[key] = item

    for i, row in enumerate(vec):
        key = row.get("chunk_id") or f"vec-{i}"
        # Avoid dup if same page+prefix already from keyword
        text = (row.get("text") or "")[:80]
        dup = False
        for existing in merged.values():
            if (
                existing.get("source_id") == row.get("source_id")
                and existing.get("page_number") == row.get("page_number")
                and (existing.get("text") or "")[:80] == text
            ):
                existing["rank_score"] = max(
                    existing.get("rank_score", 0),
                    float(row.get("score", 0)) + 0.5,
                )
                existing["retrieval"] = "hybrid"
                dup = True
                break
        if dup:
            continue
        item = dict(row)
        item["retrieval"] = "vector"
        item["rank_score"] = float(row.get("score", 0))
        merged[key] = item

    ranked = sorted(merged.values(), key=lambda x: x.get("rank_score", 0), reverse=True)
    return ranked[:merged_top_k]
