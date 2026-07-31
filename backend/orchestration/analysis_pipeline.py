"""Analysis pipeline: context → CorpusAnalyst → persist."""

from __future__ import annotations

import sqlite3

from backend.agents.corpus_analyst.agent import CorpusAnalystAgent
from backend.skills.analysis.corpus_context import build_corpus_context
from backend.storage.plan_repository import AnalysisRepository
from backend.storage.repositories import ProjectRepository


class AnalysisPipeline:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
    ) -> None:
        self.conn = conn
        self.agent = CorpusAnalystAgent(llm_mode=llm_mode)
        self.analyses = AnalysisRepository(conn)
        self.projects = ProjectRepository(conn)

    def run(self, project_id: str) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise KeyError(project_id)

        context = build_corpus_context(self.conn, project_id)
        if not context.get("sources"):
            raise ValueError("No READY evidence sources to analyze")

        analysis = self.agent.run(context)
        saved = self.analyses.save(project_id, analysis)
        self.projects.update_stage(project_id, "PLANNING")
        return {
            **saved,
            "main_topic": analysis.main_topic,
            "technical_domain": analysis.technical_domain,
            "analysis": analysis.model_dump(),
        }
