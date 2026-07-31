"""Embedding / vector index dimension safety."""

import numpy as np
import pytest

from backend.skills.retrieval.embedder import EmbeddingError, _hash_embed, index_embed_dim
from backend.skills.retrieval.vector_search import VectorStore


def test_hash_dim_is_256():
    v = _hash_embed("hello world", 256)
    assert len(v) == 256


def test_vector_store_refuses_mixed_dims(tmp_path, monkeypatch):
    monkeypatch.setenv("TAS_EMBEDDING_MODE", "hash")
    # Force offline-style hash path via settings already; VectorStore._save checks
    # mixed dims regardless.
    store = VectorStore("PRJ-TESTMIX", root=tmp_path)
    with pytest.raises(EmbeddingError):
        store._save(
            [{"chunk_id": "a", "text": "x"}, {"chunk_id": "b", "text": "y"}],
            [_hash_embed("a", 256), _hash_embed("b", 1024)],
        )


def test_wipe_and_rebuild_hash_index(tmp_path, monkeypatch):
    monkeypatch.setenv("TAS_EMBEDDING_MODE", "hash")
    store = VectorStore("PRJ-HASH", root=tmp_path)
    store.upsert_chunks(
        [
            {
                "chunk_id": "CHK-1",
                "source_id": "SRC-1",
                "page_number": 1,
                "text": "클라우드 MES 구축 사례",
                "block_ids": [],
            }
        ]
    )
    matrix = np.load(store.matrix_path)
    assert matrix.shape[1] == 256
    hits = store.search("MES")
    assert hits
