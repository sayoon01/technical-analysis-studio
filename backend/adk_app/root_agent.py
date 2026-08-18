from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from backend.adk_app.workflows.analysis_workflow import build_analysis_workflow_agent


class TechnicalAnalysisRootAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        workflow_name = str(ctx.session.state.get("workflow_name") or "analysis")
        yield Event(
            invocationId=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            actions=EventActions(
                stateDelta={"temp:workflow_transition_marker": f"root:{workflow_name}"}
            ),
            customMetadata={"event_type": "root_routing"},
        )
        if workflow_name != "analysis":
            raise ValueError(f"Unsupported workflow_name: {workflow_name}")
        analysis = self.sub_agents[0]
        async for event in analysis.run_async(ctx):
            yield event


def build_root_agent() -> TechnicalAnalysisRootAgent:
    return TechnicalAnalysisRootAgent(
        name="TechnicalAnalysisRootAgent",
        description="Deterministic workflow coordinator for technical analysis app.",
        sub_agents=[build_analysis_workflow_agent()],
    )
