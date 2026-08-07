"""Chapter-first draft and writing-context models.

Layer roles:
- ChapterWritingContext — Canonical Writer *input* (Agent Input Contract)
- ChapterDraft — Canonical Writer *output* (Agent/Domain Output)
- Chapter — optional chapter row projection (not Writer output)
Persistence Section / API sections are separate layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.domain.evidence import EvidencePack


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
    """Canonical ChapterWriterAgent output. No DB status / review / export fields."""

    chapter_id: str
    title: str
    lead: str
    subsections: list[SubsectionDraft] = Field(default_factory=list)
    chapter_conclusion: str | None = None
    key_takeaways: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    visual_intents: list[VisualIntent] = Field(default_factory=list)


class OutlineChapterRef(BaseModel):
    """Lightweight outline entry for report-level writer context."""

    node_id: str
    title: str
    objective: str = ""
    analysis_questions: list[str] = Field(default_factory=list)
    expected_length: int = 0
    order: int = 0


class ChapterSummaryMemory(BaseModel):
    chapter_id: str
    title: str
    summary: str
    key_takeaways: list[str] = Field(default_factory=list)


class ReportMemory(BaseModel):
    """Structured continuity across sequential chapters (not full prior text)."""

    established_terms: list[str] = Field(default_factory=list)
    definitions: list[str] = Field(default_factory=list)
    claims_already_explained: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    chapter_summaries: list[ChapterSummaryMemory] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)


class ChapterWritingContext(BaseModel):
    """Canonical Writer Input Contract.

    Assembled by ReportBlueprintService (Context Owner) before ChapterWriterAgent.
    Writer must not query DB/repositories/retrieval itself.
    """

    # A. Report-level
    plan_title: str | None = None
    report_language: str = "ko"
    central_thesis: str | None = None
    purpose: str | None = None
    outline_chapters: list[OutlineChapterRef] = Field(default_factory=list)

    # B. Continuity
    report_memory: ReportMemory = Field(default_factory=ReportMemory)
    prev_summary: str | None = None

    # C. Current chapter
    chapter_id: str
    title: str
    objective: str
    analysis_questions: list[str] = Field(default_factory=list)
    next_title: str | None = None
    next_objective: str | None = None
    evidence_pack: EvidencePack
    format_notes: str | None = None
    target_words: int = 0


class Chapter(BaseModel):
    chapter_id: str
    edition_id: str
    chapter_key: str
    title: str
    order_index: int
    status: str = "DRAFT"
    created_at: datetime | None = None
    updated_at: datetime | None = None
