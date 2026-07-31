"""File-backed vector index per project (numpy).

Index vectors and query vectors must share one dimension (bge-m3 → 1024).
Hash fallback vectors are never written into an Ollama-backed index.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.skills.retrieval.embedder import (
    EmbeddingError,
    embed_text,
    index_embed_dim,
    use_ollama_embeddings,
)

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, project_id: str, root: Path | None = None) -> None:
        self.project_id = project_id
        self.root = (root or Path(settings.vector_index_dir)) / project_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "meta.jsonl"
        self.matrix_path = self.root / "vectors.npy"

    def clear(self) -> None:
        """Delete on-disk index files for this project."""
        if self.meta_path.exists():
            self.meta_path.unlink()
        if self.matrix_path.exists():
            self.matrix_path.unlink()

    def clear_source(self, source_id: str) -> None:
        rows = self._load_meta()
        kept = [r for r in rows if r.get("source_id") != source_id]
        if len(kept) == len(rows):
            return
        self._rewrite(kept)

    def upsert_chunks(self, chunks: list[dict]) -> None:
        """chunks: chunk_id, source_id, page_number, text, block_ids, page_type?"""
        if not chunks:
            return
        existing = self._load_meta()
        source_ids = {c["source_id"] for c in chunks}
        kept = [r for r in existing if r.get("source_id") not in source_ids]

        new_meta = []
        new_vecs = []
        for c in chunks:
            vec = self._embed(c["text"])
            new_meta.append(
                {
                    "chunk_id": c["chunk_id"],
                    "source_id": c["source_id"],
                    "page_number": c["page_number"],
                    "block_ids": c.get("block_ids", []),
                    "text": c["text"],
                    "page_type": c.get("page_type"),
                }
            )
            new_vecs.append(vec)

        all_meta = kept + new_meta
        if kept:
            # Re-embed kept rows so dim stays consistent with new vectors
            vectors = [self._embed(r["text"]) for r in kept] + new_vecs
        else:
            vectors = new_vecs

        self._save(all_meta, vectors)

    def rebuild(self) -> dict:
        """Re-embed all meta texts with the current embedding backend."""
        meta = self._load_meta()
        if not meta:
            self.clear()
            return {"project_id": self.project_id, "chunks": 0, "dim": None}
        vectors = [self._embed(r.get("text") or "") for r in meta]
        self._save(meta, vectors)
        dim = len(vectors[0]) if vectors else None
        return {"project_id": self.project_id, "chunks": len(meta), "dim": dim}

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        source_ids: list[str] | None = None,
    ) -> list[dict]:
        meta = self._load_meta()
        if not meta:
            return []
        matrix = self._load_matrix()
        q = np.array(self._embed(query), dtype=np.float32)

        needs_rebuild = (
            matrix is None
            or len(matrix) != len(meta)
            or matrix.ndim != 2
            or matrix.shape[1] != q.shape[0]
        )
        if needs_rebuild:
            logger.warning(
                "vector index dim/length mismatch for %s (matrix=%s query_dim=%s); rebuilding",
                self.project_id,
                None if matrix is None else getattr(matrix, "shape", None),
                int(q.shape[0]),
            )
            matrix = np.array(
                [self._embed(r.get("text") or "") for r in meta],
                dtype=np.float32,
            )
            np.save(self.matrix_path, matrix)
            q = np.array(self._embed(query), dtype=np.float32)

        if matrix.ndim != 2 or matrix.shape[1] != q.shape[0]:
            raise EmbeddingError(
                f"vector search dim mismatch after rebuild: "
                f"index={matrix.shape if matrix is not None else None}, "
                f"query={q.shape[0]}. Delete the index and rebuild with bge-m3."
            )

        scores = matrix @ q
        ranked = sorted(enumerate(scores.tolist()), key=lambda x: x[1], reverse=True)
        out: list[dict] = []
        for idx, score in ranked:
            row = dict(meta[idx])
            if source_ids and row["source_id"] not in source_ids:
                continue
            row["score"] = float(score)
            out.append(row)
            if len(out) >= top_k:
                break
        return out

    def _embed(self, text: str) -> list[float]:
        # Strict in Ollama mode: never persist hash(256) into the index.
        return embed_text(text, dim=index_embed_dim() if use_ollama_embeddings() else None)

    def _load_meta(self) -> list[dict]:
        if not self.meta_path.exists():
            return []
        rows = []
        for line in self.meta_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _load_matrix(self) -> np.ndarray | None:
        if not self.matrix_path.exists():
            return None
        return np.load(self.matrix_path)

    def _save(self, meta: list[dict], vectors: list[list[float]]) -> None:
        if vectors:
            dims = {len(v) for v in vectors}
            if len(dims) != 1:
                raise EmbeddingError(
                    f"refusing to save mixed embedding dims {sorted(dims)} "
                    f"for project {self.project_id}"
                )
            dim = next(iter(dims))
            if use_ollama_embeddings() and dim != index_embed_dim():
                raise EmbeddingError(
                    f"refusing to save dim={dim} into Ollama index "
                    f"(expected {index_embed_dim()}) for {self.project_id}"
                )
        with self.meta_path.open("w", encoding="utf-8") as f:
            for row in meta:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if vectors:
            np.save(self.matrix_path, np.array(vectors, dtype=np.float32))
        elif self.matrix_path.exists():
            self.matrix_path.unlink()

    def _rewrite(self, meta: list[dict]) -> None:
        if not meta:
            self.clear()
            return
        vectors = [self._embed(r.get("text") or "") for r in meta]
        self._save(meta, vectors)


def rebuild_all_indexes(*, root: Path | None = None) -> list[dict]:
    """Rebuild every project index under the vector root from meta.jsonl texts."""
    base = root or Path(settings.vector_index_dir)
    if not base.exists():
        return []
    results = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        store = VectorStore(child.name, root=base)
        try:
            results.append({"ok": True, **store.rebuild()})
        except Exception as e:
            logger.exception("rebuild failed for %s", child.name)
            results.append(
                {"ok": False, "project_id": child.name, "error": str(e)}
            )
    return results


def wipe_mismatched_matrices(*, root: Path | None = None, expected_dim: int | None = None) -> int:
    """Delete vectors.npy whose column dim != expected (meta.jsonl kept for rebuild)."""
    base = root or Path(settings.vector_index_dir)
    exp = expected_dim or index_embed_dim()
    removed = 0
    if not base.exists():
        return 0
    for child in base.iterdir():
        path = child / "vectors.npy"
        if not path.exists():
            continue
        try:
            matrix = np.load(path)
        except Exception:
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if matrix.ndim != 2 or matrix.shape[1] != exp:
            path.unlink(missing_ok=True)
            removed += 1
            logger.info(
                "removed mismatched index %s shape=%s (expected dim=%s)",
                path,
                getattr(matrix, "shape", None),
                exp,
            )
    return removed
