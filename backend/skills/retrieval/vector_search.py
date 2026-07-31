"""File-backed vector index per project (numpy)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.skills.retrieval.embedder import embed_text


class VectorStore:
    def __init__(self, project_id: str, root: Path | None = None) -> None:
        self.project_id = project_id
        self.root = (root or Path(settings.vector_index_dir)) / project_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "meta.jsonl"
        self.matrix_path = self.root / "vectors.npy"

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
            vec = embed_text(c["text"])
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
            old_matrix = self._load_matrix()
            # Rebuild matrix aligned with kept+new — simpler to re-embed kept texts
            vectors = [embed_text(r["text"]) for r in kept] + new_vecs
        else:
            vectors = new_vecs

        self._save(all_meta, vectors)

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
        if matrix is None or len(matrix) != len(meta):
            # rebuild
            matrix = np.array([embed_text(r["text"]) for r in meta], dtype=np.float32)
            np.save(self.matrix_path, matrix)

        q = np.array(embed_text(query), dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != q.shape[0]:
            # Dim changed (e.g. hash→bge-m3): rebuild index in place
            matrix = np.array([embed_text(r["text"]) for r in meta], dtype=np.float32)
            np.save(self.matrix_path, matrix)
            q = np.array(embed_text(query), dtype=np.float32)
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
        with self.meta_path.open("w", encoding="utf-8") as f:
            for row in meta:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if vectors:
            np.save(self.matrix_path, np.array(vectors, dtype=np.float32))
        elif self.matrix_path.exists():
            self.matrix_path.unlink()

    def _rewrite(self, meta: list[dict]) -> None:
        vectors = [embed_text(r["text"]) for r in meta]
        self._save(meta, vectors)
