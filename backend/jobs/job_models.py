from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AnalyzeJob:
    job_id: str
    project_id: str
    job_type: str
    status: str
    phase: str
    payload_json: str
    adk_app_name: str
    adk_user_id: str
    adk_session_id: str
    adk_invocation_id: str | None
    current_workflow: str | None
    current_agent: str | None
    current_chapter: str | None
    last_event_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    result_json: str | None


@dataclass(slots=True)
class JobEventRow:
    job_event_id: str
    job_id: str
    sequence_no: int
    event_type: str
    workflow_name: str | None
    agent_name: str | None
    invocation_id: str | None
    session_id: str | None
    progress: float | None
    sanitized_error_code: str | None
    created_at: str
    payload: dict[str, Any] | None = None
