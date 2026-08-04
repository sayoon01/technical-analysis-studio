"""Blueprint models used after title/outline approval."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubsectionBlueprint(BaseModel):
    subsection_id: str
    title: str
    objective: str
    evidence_theme_ids: list[str] = Field(default_factory=list)


class ChapterBlueprint(BaseModel):
    chapter_id: str
    title: str
    objective: str
    core_message: str
    questions_to_answer: list[str] = Field(default_factory=list)
    subsections: list[SubsectionBlueprint] = Field(default_factory=list)
    evidence_theme_ids: list[str] = Field(default_factory=list)
    target_words: int = 0
    planned_visual_types: list[str] = Field(default_factory=list)
    transition_from_previous: str | None = None
    transition_to_next: str | None = None


class ReportBlueprint(BaseModel):
    approved_title: str
    approved_subtitle: str | None = None
    central_thesis: str
    executive_summary_points: list[str] = Field(default_factory=list)
    terminology: dict[str, str] = Field(default_factory=dict)
    chapters: list[ChapterBlueprint] = Field(default_factory=list)
    overall_limitations: list[str] = Field(default_factory=list)
