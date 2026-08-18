from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from google.genai import types
from google.adk.apps.app import App
from google.adk.runners import Runner

from backend.adk_app.artifact_service import build_artifact_service
from backend.adk_app.root_agent import build_root_agent
from backend.adk_app.session_service import build_session_service


def build_runner(app_name: str) -> Runner:
    app = App(name=app_name, root_agent=build_root_agent())
    return Runner(
        app=app,
        session_service=build_session_service(),
        artifact_service=build_artifact_service(),
    )


def run_analyze_job_sync(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    invocation_id: str,
    initial_state: dict[str, Any],
    on_event,
) -> dict[str, Any]:
    return asyncio.run(
        run_analyze_job_async(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            invocation_id=invocation_id,
            initial_state=initial_state,
            on_event=on_event,
        )
    )


async def run_analyze_job_async(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    invocation_id: str,
    initial_state: dict[str, Any],
    on_event,
) -> dict[str, Any]:
    runner = build_runner(app_name)
    ss = runner.session_service
    session = await ss.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        await ss.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state=initial_state,
        )
    else:
        # push initial state through run state_delta for traceability
        pass

    msg = types.Content(role="user", parts=[types.Part(text="run analyze workflow")])
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        invocation_id=invocation_id,
        new_message=msg,
        state_delta=initial_state,
    ):
        on_event(event)

    final_session = await ss.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    state = (final_session.state if final_session else {}) or {}
    return {
        "source_intelligence_raw": state.get("source_intelligence_raw"),
        "source_intelligence_validated": state.get("source_intelligence_validated"),
        "evidence_decision_raw": state.get("evidence_decision_raw"),
        "evidence_decision_validated": state.get("evidence_decision_validated"),
    }
