"""Phase 3: Canonical chapter writing contract.

ONE_CANONICAL_WRITER_PATH / INPUT / OUTPUT
Context Owner = ReportBlueprintService
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.agents.chapter_writer.agent import ChapterWriterAgent
from backend.agents.prompt_loader import load_agent_instruction
from backend.domain.chapter import (
    ChapterDraft,
    ChapterWritingContext,
    ReportMemory,
)
from backend.domain.evidence import EvidencePack
from backend.orchestration.production_pipeline import ProductionPipeline
from backend.services.report_blueprint_service import (
    ChapterBlueprintUnit,
    ReportBlueprintService,
)
from backend.skills.analysis.draft_validator import validate_draft


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
AGENTS_DIR = BACKEND / "agents"
PROMPTS_DIR = ROOT / "prompts" / "technical_analysis"


def test_pipeline_context_owner_then_writer():
    src = inspect.getsource(ProductionPipeline._produce_section)
    ctx_at = src.index("self.blueprints.build_writing_context")
    writer_at = src.index("self.writer.run")
    validate_at = src.index("validate_draft")
    assert ctx_at < writer_at < validate_at
    assert "ChapterWritingContext" in inspect.getsource(
        ReportBlueprintService.build_writing_context
    )


def test_writer_input_contract_is_chapter_writing_context():
    sig = inspect.signature(ChapterWriterAgent.run)
    ann = sig.parameters["ctx"].annotation
    assert ann is ChapterWritingContext or ann == "ChapterWritingContext"
    # Required conceptual fields present on schema
    fields = set(ChapterWritingContext.model_fields)
    for required in {
        "plan_title",
        "outline_chapters",
        "report_memory",
        "prev_summary",
        "chapter_id",
        "title",
        "objective",
        "analysis_questions",
        "evidence_pack",
        "target_words",
        "report_language",
        "next_objective",
    }:
        assert required in fields


def test_writer_output_is_chapter_draft_only():
    writer = ChapterWriterAgent(llm_mode="offline")
    ctx = ChapterWritingContext(
        chapter_id="CH-X",
        title="t",
        objective="o",
        evidence_pack=EvidencePack(section_id="S", section_objective="o"),
        outline_chapters=[],
    )
    draft = writer.run(ctx)
    assert isinstance(draft, ChapterDraft)
    assert not hasattr(draft, "status")
    assert not hasattr(draft, "edition_id")


def test_writer_does_not_import_repositories_or_retrieval():
    path = AGENTS_DIR / "chapter_writer" / "agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned_prefixes = (
        "backend.storage",
        "backend.services.evidence_pack",
        "backend.skills.retrieval",
        "backend.orchestration",
    )
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(banned_prefixes):
                hits.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(banned_prefixes):
                    hits.append(alias.name)
    assert hits == [], hits
    text = path.read_text(encoding="utf-8")
    assert "PlanRepository" not in text
    assert "build_evidence_pack" not in text


def test_writer_uses_generate_structured_not_direct_call_ollama_json():
    text = (AGENTS_DIR / "chapter_writer" / "agent.py").read_text(encoding="utf-8")
    assert "generate_structured" in text
    assert "call_ollama_json" not in text


def test_single_writer_prompt_source_of_truth():
    assert (PROMPTS_DIR / "chapter_writer.md").is_file()
    instruction = load_agent_instruction("chapter_writer")
    assert "ChapterWritingContext" in instruction or "Chapter Draft" in instruction or "ChapterDraft" in instruction
    # no parallel writer prompts
    for name in ("technical_writer.md", "writer_v2.md", "chapter_generation.md"):
        assert not (PROMPTS_DIR / name).exists()


def test_no_parallel_writer_packages():
    assert (AGENTS_DIR / "chapter_writer" / "agent.py").is_file()
    for banned in ("technical_writer", "writer_v2", "chapter_generation_agent", "adk_writer_new"):
        assert not (AGENTS_DIR / banned).exists()


def test_no_duplicate_writer_output_schema_names():
    """Domain Writer output schema name ChapterDraft appears once as class def in domain."""
    hits = []
    for path in BACKEND.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "class WriterOutput" in text or "class GeneratedSection" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], hits


def test_blueprint_builds_full_writing_context_with_evidence():
    svc = ReportBlueprintService()
    units = svc.build_from_outline(
        outline_nodes=[
            {
                "node_id": "N1",
                "parent_id": None,
                "level": 1,
                "order": 1,
                "title": "배경",
                "objective": "배경 분석",
                "analysis_questions": ["왜?"],
                "expected_length": 500,
            },
            {
                "node_id": "N2",
                "parent_id": None,
                "level": 1,
                "order": 2,
                "title": "성과",
                "objective": "성과 분석",
                "analysis_questions": ["얼마?"],
                "expected_length": 600,
            },
        ]
    )
    pack = EvidencePack(section_id="SEC-1", section_objective="성과 분석")
    ctx = svc.build_writing_context(
        plan={
            "title": "보고서",
            "purpose": "목적",
            "plan": {"central_thesis": "핵심 논지", "terminology_policy": {"MES": "제조실행시스템"}},
        },
        chapter_units=units,
        node={
            "node_id": "N2",
            "title": "성과",
            "objective": "성과 분석",
            "analysis_questions": ["얼마?"],
            "expected_length": 600,
        },
        chapter=units[1],
        pack=pack,
        report_memory=ReportMemory(),
        prev_summary="이전 장 요약",
        next_title=None,
        next_objective=None,
    )
    assert isinstance(ctx, ChapterWritingContext)
    assert ctx.evidence_pack.section_id == "SEC-1"
    assert len(ctx.outline_chapters) == 2
    assert ctx.outline_chapters[0].title == "배경"
    assert ctx.target_words == 600
    assert ctx.central_thesis == "핵심 논지"
    assert any("MES" in t for t in ctx.report_memory.established_terms)
    assert ctx.prev_summary == "이전 장 요약"


def test_report_memory_extends_without_full_prior_text():
    svc = ReportBlueprintService()
    memory = ReportMemory()
    draft = ChapterDraft(
        chapter_id="CH-01",
        title="배경",
        lead="lead",
        key_takeaways=["핵심1"],
        limitations=["한계1"],
    )
    updated = svc.extend_report_memory(
        memory, draft=draft, summary="요약 " * 100
    )
    assert len(updated.chapter_summaries) == 1
    assert len(updated.chapter_summaries[0].summary) <= 400
    assert "핵심1" in updated.key_findings


def test_draft_validator_empty_content():
    result = validate_draft(
        section_id="SEC-1",
        markdown="   ",
        pack=EvidencePack(section_id="SEC-1", section_objective="o"),
    )
    assert not result.ok
    assert any(i.issue_type == "EMPTY_CONTENT" for i in result.issues)


def test_chapter_writer_agent_is_sole_pipeline_writer():
    init_src = inspect.getsource(ProductionPipeline.__init__)
    assert "ChapterWriterAgent" in init_src
    assert "TechnicalWriter" not in init_src
    produce_src = inspect.getsource(ProductionPipeline._produce_section)
    assert "self.writer.run" in produce_src
    assert "write_section_offline" not in produce_src  # offline only inside agent


def test_resume_skip_complete_sections_predicate():
    complete = {"status": "DRAFT", "content_markdown": "x" * 50}
    incomplete = {"status": "WRITING", "content_markdown": "x" * 50}
    empty = {"status": "DRAFT", "content_markdown": "short"}
    assert ProductionPipeline._section_is_complete(complete)
    assert not ProductionPipeline._section_is_complete(incomplete)
    assert not ProductionPipeline._section_is_complete(empty)
