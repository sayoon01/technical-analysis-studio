"""Planning strategy models for chapter-first report design."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TitleCandidate(BaseModel):
    title: str
    style: Literal["SOURCE_PRESERVING", "ANALYTICAL", "CONCISE"]
    rationale: str | None = None


class EvidenceTheme(BaseModel):
    theme_id: str
    theme_type: str
    label: str
    summary: str
    importance: Literal["CORE", "SUPPORTING", "MINOR"] = "SUPPORTING"
    evidence_ids: list[str] = Field(default_factory=list)
    related_theme_ids: list[str] = Field(default_factory=list)
    suggested_use: Literal[
        "CHAPTER",
        "SUBSECTION",
        "TABLE",
        "VISUAL",
        "LIMITATION_ONLY",
    ] = "SUBSECTION"


class ReportStrategy(BaseModel):
    source_title: str | None = None
    title_candidates: list[TitleCandidate] = Field(default_factory=list)
    recommended_title: str
    subtitle: str | None = None
    target_reader: str
    purpose: str
    central_thesis: str
    narrative_arc: list[str] = Field(default_factory=list)
    included_scope: list[str] = Field(default_factory=list)
    excluded_scope: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    recommended_pages: int = 0
    recommended_chapter_count: int = 0
    recommended_visual_count: int = 0
