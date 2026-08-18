from __future__ import annotations

from google.adk.events.event import Event


def projectable_event_type(event: Event) -> str:
    if getattr(event, "error_code", None) or getattr(event, "errorCode", None):
        return "error"
    state_delta = None
    if event.actions:
        state_delta = getattr(event.actions, "stateDelta", None) or getattr(
            event.actions, "state_delta", None
        )
    if state_delta:
        return "state_delta"
    if event.author == "user":
        return "user"
    if event.content and event.content.parts:
        return "agent_output"
    return "system"


def event_progress(event: Event) -> float | None:
    # Keep projection minimal; no raw payload copy.
    if not event.actions:
        return None
    state_delta = getattr(event.actions, "stateDelta", None) or getattr(
        event.actions, "state_delta", None
    )
    if not state_delta:
        return None
    marker = state_delta.get("temp:workflow_transition_marker")
    if marker in {"analysis_started", "root:analysis"}:
        return 0.1
    if marker == "source_validated":
        return 0.5
    if marker == "analysis_completed":
        return 1.0
    return None


def sanitized_error_code(event: Event) -> str | None:
    code = getattr(event, "error_code", None) or getattr(event, "errorCode", None)
    if not code:
        return None
    return str(code)[:64]
