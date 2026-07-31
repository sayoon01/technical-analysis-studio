"""Rebuild project vector indexes with the current embedding model (bge-m3).

Usage:
  PYTHONPATH=. python scripts/rebuild_vector_indexes.py
  PYTHONPATH=. python scripts/rebuild_vector_indexes.py --project PRJ-44D639AD85
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.skills.retrieval.embedder import index_embed_dim, use_ollama_embeddings
from backend.skills.retrieval.vector_search import (
    VectorStore,
    rebuild_all_indexes,
    wipe_mismatched_matrices,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="Rebuild only this project_id")
    parser.add_argument(
        "--wipe-only",
        action="store_true",
        help="Only delete mismatched vectors.npy files",
    )
    args = parser.parse_args()

    print(
        "embedding_mode",
        "ollama" if use_ollama_embeddings() else "hash",
        "index_dim",
        index_embed_dim(),
    )
    removed = wipe_mismatched_matrices()
    print(f"wiped_mismatched_matrices={removed}")
    if args.wipe_only:
        return 0

    if args.project:
        result = VectorStore(args.project).rebuild()
        print(result)
        return 0

    results = rebuild_all_indexes()
    ok = sum(1 for r in results if r.get("ok"))
    bad = [r for r in results if not r.get("ok")]
    print(f"rebuilt_ok={ok} failed={len(bad)}")
    for r in bad[:20]:
        print("FAIL", r)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
