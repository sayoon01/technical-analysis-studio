"""ReportStrategistAgent — title candidates and report direction."""

from __future__ import annotations

import json

from backend.agents.prompt_loader import load_agent_instruction
from backend.config import settings
from backend.domain.report_plan import CorpusAnalysis
from backend.domain.strategy import ReportStrategy, TitleCandidate
from backend.model_providers.base import (
    LlmError,
    allow_offline_fallback,
    generate_structured,
)


class ReportStrategistAgent:
    def __init__(self, *, llm_mode: str | None = None) -> None:
        self.llm_mode = (llm_mode or settings.llm_mode).lower()

    def run(self, analysis: CorpusAnalysis) -> ReportStrategy:
        if self.llm_mode == "offline":
            return _offline_strategy(analysis)
        try:
            instruction = load_agent_instruction("report_strategist")
            user = (
                "Create ReportStrategy JSON from this corpus analysis.\n"
                "Return Korean titles and avoid ellipsis.\n\n"
                f"{json.dumps(analysis.model_dump(), ensure_ascii=False)}"
            )
            strategy = generate_structured(
                ReportStrategy,
                instruction,
                user,
                agent_name="report_strategist",
                max_retries=1,
            )
            if not strategy.title_candidates:
                strategy.title_candidates = _offline_title_candidates(analysis.main_topic)
            if not strategy.recommended_title:
                strategy.recommended_title = strategy.title_candidates[0].title
            return strategy
        except LlmError:
            if not allow_offline_fallback():
                raise
            return _offline_strategy(analysis)


def _offline_title_candidates(topic: str) -> list[TitleCandidate]:
    base = topic.strip() or "기술자료"
    return [
        TitleCandidate(
            title=f"{base} 기반 기술분석 보고서",
            style="SOURCE_PRESERVING",
            rationale="원문 주제를 보존해 제목 왜곡을 줄인다.",
        ),
        TitleCandidate(
            title=f"{base} 구축 사례 및 성과 분석",
            style="ANALYTICAL",
            rationale="구축 흐름과 성과 해석을 함께 반영한다.",
        ),
        TitleCandidate(
            title=f"{base} 전환 분석",
            style="CONCISE",
            rationale="핵심 메시지를 짧게 전달한다.",
        ),
    ]


def _offline_strategy(analysis: CorpusAnalysis) -> ReportStrategy:
    titles = _offline_title_candidates(analysis.main_topic)
    return ReportStrategy(
        source_title=analysis.main_topic,
        title_candidates=titles,
        recommended_title=titles[0].title,
        subtitle=analysis.document_purpose,
        target_reader="기술·기획 의사결정자",
        purpose=analysis.document_purpose or "기술자료 기반 분석",
        central_thesis=(analysis.recommended_report_focus or ["자료 기반 핵심 이슈를 분석한다."])[0],
        narrative_arc=list(analysis.recommended_report_focus[:4]),
        included_scope=list(analysis.recommended_report_focus[:4]),
        excluded_scope=[],
        evidence_limitations=list(analysis.evidence_gaps[:5]),
        recommended_pages=20,
        recommended_chapter_count=6,
        recommended_visual_count=4,
    )
