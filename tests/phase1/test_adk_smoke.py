from __future__ import annotations

import os

import pytest

from backend.adk_app.runner import AdkRunConfig, AdkRunner


def test_runner_returns_planned_envelope():
    runner = AdkRunner()
    result = runner.run(
        AdkRunConfig(workflow_name="planning_workflow", project_id="PRJ-TEST")
    )
    assert result["status"] == "PLANNED"
    assert result["project_id"] == "PRJ-TEST"


def test_litellm_factory_builds_ollama_chat_model(monkeypatch):
    pytest.importorskip("google.adk")
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")

    runner = AdkRunner()
    model = runner.build_model()
    model_name = getattr(model, "model", "") or getattr(model, "model_name", "")
    assert str(model_name).startswith("ollama_chat/")
    assert "gemma4:31b" in str(model_name)


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_SMOKE") != "1",
    reason="Set RUN_OLLAMA_SMOKE=1 to ping real Ollama endpoint.",
)
def test_litellm_model_can_initialize_with_real_ollama():
    pytest.importorskip("google.adk")
    runner = AdkRunner()
    model = runner.build_model()
    assert model is not None
