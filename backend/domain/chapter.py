"""Chapter-first draft and storage models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VisualIntent(BaseModel):
    visual_type: str
    purpose: str
    related_evidence_ids: list[str] = Field(default_factory=list)
    preferred_position: str = "AFTER_SUBSECTION"


class DraftParagraph(BaseModel):
    paragraph_id: str
    paragraph_type: Literal["FACT", "SYNTHESIS", "ANALYSIS", "LIMITATION"]
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class SubsectionDraft(BaseModel):
    subsection_id: str
    title: str
    paragraphs: list[DraftParagraph] = Field(default_factory=list)


class ChapterDraft(BaseModel):
    chapter_id: str
    title: str
    lead: str
    subsections: list[SubsectionDraft] = Field(default_factory=list)
    chapter_conclusion: str | None = None
    key_takeaways: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    visual_intents: list[VisualIntent] = Field(default_factory=list)


class Chapter(BaseModel):
    chapter_id: str
    edition_id: str
    chapter_key: str
    title: str
    order_index: int
    status: str = "DRAFT"
    created_at: datetime | None = None
    updated_at: datetime | None = None
