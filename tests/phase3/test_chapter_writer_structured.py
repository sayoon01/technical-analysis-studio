from __future__ import annotations

from backend.agents.chapter_writer.agent import ChapterWriterAgent, render_chapter_markdown
from backend.domain.evidence import EvidencePack


def test_chapter_writer_returns_structured_draft_offline(monkeypatch):
    monkeypatch.setenv("TAS_LLM_MODE", "offline")
    writer = ChapterWriterAgent(llm_mode="offline")
    draft = writer.run(
        chapter_id="CH-01",
        title="정량 성과",
        objective="핵심 지표를 요약한다.",
        pack=EvidencePack(section_id="SEC-1", section_objective="o"),
    )
    assert draft.chapter_id == "CH-01"
    assert draft.subsections
    assert draft.subsections[0].paragraphs


def test_render_chapter_markdown_strips_internal_markers():
    writer = ChapterWriterAgent(llm_mode="offline")
    draft = writer.run(
        chapter_id="CH-02",
        title="검증",
        objective="본문 검증",
        pack=EvidencePack(section_id="SEC-2", section_objective="o"),
    )
    # emulate bad legacy marker
    draft.subsections[0].paragraphs[0].text = "<!-- P-INFRA-01 --> 본문"
    md = render_chapter_markdown(draft, heading_level=2)
    assert "<!--" not in md
    assert "P-INFRA-" not in md
