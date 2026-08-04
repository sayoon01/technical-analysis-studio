from __future__ import annotations

import os

import pytest

from backend.skills.retrieval.embedder import embed_text


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_SMOKE") != "1",
    reason="Set RUN_OLLAMA_SMOKE=1 to run Ollama smoke tests.",
)


def test_ollama_embedding_smoke(monkeypatch):
    monkeypatch.setenv("TAS_LLM_MODE", "llm")
    monkeypatch.setenv("TAS_EMBEDDING_MODE", "ollama")
    vec = embed_text("MES 구축 효과 검증", strict=True)
    assert isinstance(vec, list)
    assert len(vec) > 0
