from __future__ import annotations

import json

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from backend.adk_app.model_adapter import build_agent_model


def _instruction(ctx: ReadonlyContext) -> str:
    state = dict(ctx.state)
    validated = state.get("source_intelligence_validated") or {}
    candidates = state.get("evidence_candidates") or []
    rules = state.get("evidence_rules") or {}
    repair = state.get("repair_request") or {}
    repair_piece = repair.get("evidence_decision")
    repair_text = ""
    if isinstance(repair_piece, dict):
        repair_text = (
            "\n\n[REPAIR]\n"
            + json.dumps(repair_piece, ensure_ascii=False)
            + "\nReturn corrected JSON only."
        )
    return (
        "You are EvidenceCuratorAgent.\n"
        "Produce JSON string only. No markdown.\n"
        "status must be one of: accepted, rejected, failed.\n"
        "Schema:\n"
        "{"
        '"decisions":[{"evidence_id":str,"status":"accepted|rejected|failed","reason":str|null}],'
        '"accepted_count":int,'
        '"rejected_count":int,'
        '"failed_count":int'
        "}\n\n"
        f"[SOURCE_INTELLIGENCE_VALIDATED]\n{json.dumps(validated, ensure_ascii=False)}\n\n"
        f"[EVIDENCE_CANDIDATES]\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
        f"[RULES]\n{json.dumps(rules, ensure_ascii=False)}"
        f"{repair_text}"
    )


def build_evidence_curator_agent() -> LlmAgent:
    return LlmAgent(
        name="EvidenceCuratorAgent",
        description="Decide accepted/rejected/failed evidence candidates.",
        model=build_agent_model("technical_reviewer"),
        instruction=_instruction,
        include_contents="none",
        output_key="evidence_decision_raw",
        output_schema=str,
    )
