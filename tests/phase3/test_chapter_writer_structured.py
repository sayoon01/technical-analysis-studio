from __future__ import annotations

from backend.agents.chapter_writer.agent import ChapterWriterAgent, render_chapter_markdown
from backend.domain.chapter import ChapterWritingContext
from backend.domain.evidence import EvidencePack


def _ctx(**overrides) -> ChapterWritingContext:
    base = dict(
        chapter_id="CH-01",
        title="정량 성과",
        objective="핵심 지표를 요약한다.",
        evidence_pack=EvidencePack(section_id="SEC-1", section_objective="o"),
        plan_title="테스트 보고서",
        report_language="ko",
        analysis_questions=["핵심 수치는?"],
        target_words=400,
    )
    base.update(overrides)
    return ChapterWritingContext(**base)


def test_chapter_writer_returns_structured_draft_offline(monkeypatch):
    monkeypatch.setenv("TAS_LLM_MODE", "offline")
    writer = ChapterWriterAgent(llm_mode="offline")
    draft = writer.run(_ctx())
    assert draft.chapter_id == "CH-01"
    assert draft.subsections
    assert draft.subsections[0].paragraphs
    assert isinstance(draft.title, str)


def test_render_chapter_markdown_strips_internal_markers():
    writer = ChapterWriterAgent(llm_mode="offline")
    draft = writer.run(_ctx(chapter_id="CH-02", title="검증", objective="본문 검증"))
    draft.subsections[0].paragraphs[0].text = "<!-- P-INFRA-01 --> 본문"
    md = render_chapter_markdown(draft, heading_level=2)
    assert "<!--" not in md
    assert "P-INFRA-" not in md


def test_writer_accepts_only_writing_context():
    import inspect

    sig = inspect.signature(ChapterWriterAgent.run)
    params = list(sig.parameters)
    assert params == ["self", "ctx"]
