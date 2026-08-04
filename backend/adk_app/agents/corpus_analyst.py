"""Corpus analyst ADK agent factory."""

from __future__ import annotations

from backend.adk_app.model_factory import build_litellm_model
from backend.adk_app.prompt_loader import load_prompt


def build_corpus_analyst_agent():
    from google.adk import Agent

    return Agent(
        name="corpus_analyst",
        model=build_litellm_model(),
        instruction=load_prompt("technical_analysis/corpus_analyst.md"),
    )
