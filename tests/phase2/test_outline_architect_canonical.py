"""Phase 2: OutlineArchitect is the sole outline-generation Canonical Owner."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.agents.outline_architect.agent import OutlineArchitectAgent
from backend.agents.outline_critic.agent import OutlineCriticAgent
from backend.agents.prompt_loader import load_agent_instruction
from backend.agents.report_strategist.agent import ReportStrategistAgent
from backend.domain.report_plan import CorpusAnalysis, OutlineNode, ReportPlan
from backend.domain.strategy import ReportStrategy, TitleCandidate
from backend.orchestration.planning_pipeline import PlanningPipeline
from backend.skills.analysis.outline_quality_gate import validate_outline


ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / "backend" / "agents"
PROMPTS_DIR = ROOT / "prompts" / "technical_analysis"


def test_pipeline_agent_order_and_types():
    """PlanningPipeline owns: Strategist → OutlineArchitect → Critic (+ Gate)."""
    src = inspect.getsource(PlanningPipeline.run)
    strategist_at = src.index("self.strategist.run")
    architect_at = src.index("self.outline_architect.run")
    critic_at = src.index("self.critic.run")
    gate_at = src.index("validate_outline")
    assert strategist_at < architect_at < critic_at < gate_at

    pipe_src = inspect.getsource(PlanningPipeline.__init__)
    assert "OutlineArchitectAgent" in pipe_src
    assert "ReportStrategistAgent" in pipe_src
    assert "OutlineCriticAgent" in pipe_src
    assert "OutlineDesigner" not in pipe_src
    assert "ReportPlanner" not in pipe_src


def test_no_legacy_outline_packages_or_imports():
    assert not (AGENTS_DIR / "outline_designer").exists()
    assert not (AGENTS_DIR / "report_planner").exists()
    assert (AGENTS_DIR / "outline_architect" / "agent.py").is_file()

    ban = (
        "OutlineDesigner",
        "OutlineDesignerAgent",
        "ReportPlanner",
        "ReportPlannerAgent",
        "outline_designer",
        "report_planner",
    )
    hits: list[str] = []
    for path in (ROOT / "backend").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ban:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}:{token}")
    assert hits == [], f"legacy outline references remain: {hits}"


def test_single_outline_prompt_source_of_truth():
    assert (PROMPTS_DIR / "outline_architect.md").is_file()
    assert not (PROMPTS_DIR / "report_planner.md").exists()
    assert not (PROMPTS_DIR / "outline_designer.md").exists()
    instruction = load_agent_instruction("outline_architect")
    assert "Outline Architect" in instruction
    assert "ReportPlan" in instruction


def test_strategy_is_applied_to_architect_output(monkeypatch):
    strategy = ReportStrategy(
        recommended_title="전략 제목",
        subtitle="전략 부제",
        central_thesis="중심 논지",
        title_candidates=[
            TitleCandidate(
                title="전략 제목",
                style="ANALYTICAL",
                rationale="r",
            )
        ],
        purpose="목적",
        target_reader="독자",
    )
    analysis = CorpusAnalysis(
        main_topic="주제",
        technical_domain="도메인",
        document_purpose="목적",
    )
    offline_plan = ReportPlan(
        title="offline-title",
        purpose="p",
        target_reader="r",
        report_summary="s",
        outline=[
            OutlineNode(
                node_id=f"N-{i}",
                level=1,
                order=i,
                title=title,
                objective="근거 기반 전문 분석",
                analysis_questions=[f"{title}의 핵심은?"],
                expected_length=800,
                source_scope=[],
                required_evidence_types=[],
                planned_visuals=[],
            )
            for i, title in enumerate(
                ["서론", "구성", "흐름", "성과", "한계"], start=1
            )
        ],
    )

    monkeypatch.setattr(
        "backend.agents.outline_architect.agent.plan_offline",
        lambda *_a, **_k: offline_plan.model_copy(deep=True),
    )
    architect = OutlineArchitectAgent(llm_mode="offline")
    result = architect.run(analysis, strategy=strategy, source_ids=["SRC-1"])
    assert result.title == "전략 제목"
    assert result.subtitle == "전략 부제"
    assert result.central_thesis == "중심 논지"
    assert result.strategy is not None
    assert result.strategy.recommended_title == "전략 제목"
    assert len(result.outline) == 5
    gate = validate_outline(result)
    assert gate.passed, gate.reasons


def test_outline_result_shape_fields_preserved():
    """HARD Frontend fields remain on ReportPlan / OutlineNode schemas."""
    plan_fields = set(ReportPlan.model_fields)
    for required in {
        "title",
        "subtitle",
        "purpose",
        "target_reader",
        "report_summary",
        "outline",
        "title_candidates",
        "central_thesis",
        "strategy",
    }:
        assert required in plan_fields
    node_fields = set(OutlineNode.model_fields)
    for required in {
        "node_id",
        "title",
        "objective",
        "analysis_questions",
        "level",
        "order",
    }:
        assert required in node_fields


def test_models_yaml_uses_outline_architect_not_report_planner():
    text = (ROOT / "config" / "models.yaml").read_text(encoding="utf-8")
    assert "outline_architect:" in text
    assert "report_planner:" not in text
    assert "report_strategist:" in text
    assert "outline_critic:" in text


def test_ast_pipeline_module_has_single_outline_owner():
    path = ROOT / "backend" / "orchestration" / "planning_pipeline.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imported.append(f"{node.module}.{alias.name}")
    assert any("outline_architect" in i for i in imported)
    assert not any("outline_designer" in i for i in imported)
    assert not any("report_planner" in i for i in imported)


def test_responsibility_boundary_classes_exist():
    assert callable(ReportStrategistAgent.run)
    assert callable(OutlineArchitectAgent.run)
    assert callable(OutlineCriticAgent.run)
    assert callable(validate_outline)


def test_recommend_node_stays_on_plan_service_not_second_agent():
    """recommend is deterministic PlanService heuristic — no second Outline agent."""
    from backend.services import plan_service as ps_mod

    src = inspect.getsource(ps_mod.PlanService.recommend_node)
    assert "OutlineArchitect" not in src
    assert "OutlineDesigner" not in src
    assert "ReportPlanner" not in src
    assert "generate_structured" not in src
    assert "objective" in src
    assert "analysis_questions" in src
