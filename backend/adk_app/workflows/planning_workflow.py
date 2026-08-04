"""Planning workflow scaffold.

Phase-4 scope:
- route corpus analysis through ADK runner entrypoint
- keep deterministic/offline behavior for test environments
"""

from __future__ import annotations

import json

from backend.adk_app.agents.corpus_analyst import build_corpus_analyst_agent
from backend.adk_app.prompt_loader import load_prompt
from backend.domain.report_plan import CorpusAnalysis
from backend.model_providers.base import LlmError, generate_structured
from backend.skills.analysis.offline_planner import analyze_offline


def workflow_name() -> str:
    return "planning_workflow"


def run_corpus_analysis(context: dict, *, mode: str) -> CorpusAnalysis:
    normalized = (mode or "").lower()
    pack = context.get("llm_pack") or {
        "pages": context.get("pages"),
        "metrics": context.get("metrics"),
        "sources": context.get("sources"),
    }

    if normalized == "offline":
        return analyze_offline(context)

    # Validate ADK factory wiring during this transition phase.
    if normalized == "adk":
        build_corpus_analyst_agent()

    instruction = load_prompt("technical_analysis/corpus_analyst.md")
    user = (
        "Analyze the following corpus context and return CorpusAnalysis JSON.\n"
        "Do not invent unsupported facts, numbers, or pages. "
        "Analysis and limitations are allowed when clearly marked.\n"
        "Keep lists short (max 12 items each).\n\n"
        f"{json.dumps(pack, ensure_ascii=False)}"
    )
    try:
        return generate_structured(
            CorpusAnalysis,
            instruction,
            user,
            agent_name="corpus_analyst",
            max_retries=1,
        )
    except LlmError:
        return analyze_offline(context)
