from __future__ import annotations

import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from backend.adk_app.agents.evidence_curator_agent import build_evidence_curator_agent
from backend.adk_app.agents.source_intelligence_agent import (
    build_source_intelligence_agent,
)
from backend.domain.adk_outputs import EvidenceDecisionOutput, SourceIntelligenceOutput

MAX_REPAIR = 1


class AnalysisWorkflowAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        yield self._state_event(
            ctx,
            {
                "temp:current_validation_gate": "source_intelligence",
                "temp:source_intelligence_repair_count": 0,
                "temp:evidence_decision_repair_count": 0,
                "temp:workflow_transition_marker": "analysis_started",
            },
            "workflow_state",
        )

        source_agent = self.sub_agents[0]
        source_ok = False
        for attempt in range(MAX_REPAIR + 1):
            async for event in source_agent.run_async(ctx):
                yield event
            raw = self._as_raw_string(ctx.session.state.get("source_intelligence_raw"))
            if not raw:
                raw = "{}"
            normalized = self._normalize_raw_json(raw)
            try:
                validated = SourceIntelligenceOutput.model_validate_json(normalized)
                yield self._state_event(
                    ctx,
                    {
                        "source_intelligence_validated": validated.model_dump(
                            mode="json"
                        ),
                        "temp:source_intelligence_repair_count": attempt,
                    },
                    "source_validated",
                )
                source_ok = True
                break
            except Exception as exc:
                if attempt >= MAX_REPAIR:
                    break
                yield self._state_event(
                    ctx,
                    {
                        "repair_request": {
                            "source_intelligence": {
                                "validation_error": str(exc),
                                "previous_raw": raw[:2000],
                            }
                        },
                        "temp:source_intelligence_repair_count": attempt + 1,
                    },
                    "source_repair_requested",
                    "VALIDATION_FAILED",
                )

        if not source_ok:
            yield self._state_event(
                ctx,
                {
                    "temp:validation_failure_marker": "source_intelligence",
                    "temp:workflow_transition_marker": "analysis_failed",
                },
                "validation_failed",
                "VALIDATION_FAILED",
            )
            raise ValueError("SourceIntelligence validation failed after repair")

        yield self._state_event(
            ctx,
            {
                "temp:current_validation_gate": "evidence_decision",
                "temp:workflow_transition_marker": "source_validated",
            },
            "workflow_state",
        )
        evidence_agent = self.sub_agents[1]
        evidence_ok = False
        for attempt in range(MAX_REPAIR + 1):
            async for event in evidence_agent.run_async(ctx):
                yield event
            raw = self._as_raw_string(ctx.session.state.get("evidence_decision_raw"))
            if not raw:
                raw = "{}"
            normalized = self._normalize_raw_json(raw)
            try:
                validated = EvidenceDecisionOutput.model_validate_json(normalized)
                yield self._state_event(
                    ctx,
                    {
                        "evidence_decision_validated": validated.model_dump(
                            mode="json"
                        ),
                        "temp:evidence_decision_repair_count": attempt,
                    },
                    "evidence_validated",
                )
                evidence_ok = True
                break
            except Exception as exc:
                if attempt >= MAX_REPAIR:
                    break
                yield self._state_event(
                    ctx,
                    {
                        "repair_request": {
                            "evidence_decision": {
                                "validation_error": str(exc),
                                "previous_raw": raw[:2000],
                            }
                        },
                        "temp:evidence_decision_repair_count": attempt + 1,
                    },
                    "evidence_repair_requested",
                    "VALIDATION_FAILED",
                )

        if not evidence_ok:
            yield self._state_event(
                ctx,
                {
                    "temp:validation_failure_marker": "evidence_decision",
                    "temp:workflow_transition_marker": "analysis_failed",
                },
                "validation_failed",
                "VALIDATION_FAILED",
            )
            raise ValueError("EvidenceDecision validation failed after repair")

        yield self._state_event(
            ctx,
            {"temp:workflow_transition_marker": "analysis_completed"},
            "workflow_completed",
        )

    def _state_event(
        self,
        ctx: InvocationContext,
        state_delta: dict,
        event_type: str,
        error_code: str | None = None,
    ) -> Event:
        return Event(
            invocationId=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            actions=EventActions(stateDelta=state_delta),
            customMetadata={"event_type": event_type},
            errorCode=error_code,
        )

    @staticmethod
    def _as_raw_string(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return ""

    @staticmethod
    def _normalize_raw_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            return text
        try:
            decoded = json.loads(text)
        except Exception:
            return text
        if isinstance(decoded, str):
            return decoded
        return json.dumps(decoded, ensure_ascii=False)


def build_analysis_workflow_agent() -> AnalysisWorkflowAgent:
    return AnalysisWorkflowAgent(
        name="AnalysisWorkflowAgent",
        description="Run source->validate->repair->evidence->validate gates.",
        sub_agents=[
            build_source_intelligence_agent(),
            build_evidence_curator_agent(),
        ],
    )
