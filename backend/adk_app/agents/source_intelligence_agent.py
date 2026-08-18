from __future__ import annotations

import json

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from backend.adk_app.model_adapter import build_agent_model


def _instruction(ctx: ReadonlyContext) -> str:
    state = dict(ctx.state)
    source_batch = state.get("source_batch") or {}
    constraints = state.get("analysis_constraints") or {}
    repair = state.get("repair_request") or {}
    repair_piece = repair.get("source_intelligence")
    repair_text = ""
    if isinstance(repair_piece, dict):
        repair_text = (
            "\n\n[REPAIR]\n"
            + json.dumps(repair_piece, ensure_ascii=False)
            + "\nReturn corrected JSON only."
        )
    return (
        "You are SourceIntelligenceAgent.\n"
        "Produce JSON string only. No markdown.\n"
        "Schema:\n"
        "{"
        '"main_topic": str,'
        '"technical_domain": str,'
        '"document_purpose": str|null,'
        '"key_entities": [str],'
        '"key_technologies": [str],'
        '"business_or_technical_problems": [str],'
        '"system_components": [str],'
        '"processes": [str],'
        '"qualitative_findings": [str],'
        '"evidence_gaps": [str],'
        '"contradictions": [str],'
        '"recommended_report_focus": [str]'
        "}\n\n"
        f"[SOURCE_BATCH]\n{json.dumps(source_batch, ensure_ascii=False)}\n\n"
        f"[CONSTRAINTS]\n{json.dumps(constraints, ensure_ascii=False)}"
        f"{repair_text}"
    )


def build_source_intelligence_agent() -> LlmAgent:
    return LlmAgent(
        name="SourceIntelligenceAgent",
        description="Analyze corpus meaning and limitations.",
        model=build_agent_model("corpus_analyst"),
        instruction=_instruction,
        include_contents="none",
        output_key="source_intelligence_raw",
        output_schema=str,
    )
