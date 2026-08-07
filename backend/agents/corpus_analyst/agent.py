"""CorpusAnalystAgent — semantic analysis over parsed corpus context."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.report_plan import CorpusAnalysis
from backend.model_providers.base import (
    LlmError,
    allow_offline_fallback,
    generate_structured,
)
from backend.skills.analysis.offline_planner import analyze_offline


class CorpusAnalystAgent:
    """Canonical Source Intelligence owner.

    TAS_LLM_MODE:
    - offline → deterministic analyze_offline
    - llm / adk → generate_structured via model_providers
      (adk is a compatibility alias until Phase 6 ADK execution ownership)
    """

    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(self, context: dict) -> CorpusAnalysis:
        if self.llm_mode == "offline":
            return analyze_offline(context)
        # llm and adk share this path — no separate ADK corpus workflow.
        try:
            instruction = load_agent_instruction("corpus_analyst")
            pack = context.get("llm_pack") or {
                "pages": context.get("pages"),
                "metrics": context.get("metrics"),
                "sources": context.get("sources"),
            }
            user = (
                "Analyze the following corpus context and return CorpusAnalysis JSON.\n"
                "Do not invent unsupported facts, numbers, or pages. "
                "Analysis and limitations are allowed when clearly marked.\n"
                "Keep lists short (max 12 items each).\n\n"
                f"{json.dumps(pack, ensure_ascii=False)}"
            )
            return generate_structured(
                CorpusAnalysis,
                instruction,
                user,
                agent_name="corpus_analyst",
                max_retries=1,
            )
        except LlmError:
            if not allow_offline_fallback():
                raise
            # Safe fallback — still corpus-driven, not a fixed outline
            return analyze_offline(context)
