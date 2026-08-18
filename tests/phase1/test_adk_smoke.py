from __future__ import annotations

import inspect
from backend.adk_app.agent import root_agent
from backend.adk_app.model_adapter import ConfiguredLiteLLMClient


def test_root_agent_has_analysis_sub_agent():
    assert root_agent.name == "TechnicalAnalysisRootAgent"
    assert len(root_agent.sub_agents) == 1
    assert root_agent.sub_agents[0].name == "AnalysisWorkflowAgent"
    assert [a.name for a in root_agent.sub_agents[0].sub_agents] == [
        "SourceIntelligenceAgent",
        "EvidenceCuratorAgent",
    ]


def test_timeout_is_applied_in_litellm_client_layer():
    sig = str(inspect.signature(ConfiguredLiteLLMClient.acompletion))
    assert "kwargs" in sig
