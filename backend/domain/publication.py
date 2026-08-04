"""Publication document structures for export rendering."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutiveSummary(BaseModel):
    overview: str
    highlights: list[str] = Field(default_factory=list)


class KeyResult(BaseModel):
    label: str
    value: str
    interpretation: str | None = None


class PublicationFigure(BaseModel):
    visual_id: str
    title: str
    caption: str
    source_pages: list[int] = Field(default_factory=list)
    asset_path: str | None = None


class PublicationTable(BaseModel):
    table_id: str
    title: str
    caption: str
    rows: list[list[str]] = Field(default_factory=list)


class PublicationChapter(BaseModel):
    chapter_id: str
    title: str
    body_markdown: str


class ReferenceEntry(BaseModel):
    reference_id: str
    label: str
    source_id: str
    pages: list[int] = Field(default_factory=list)


class PublicationDocument(BaseModel):
    title: str
    subtitle: str | None = None
    executive_summary: ExecutiveSummary
    key_results: list[KeyResult] = Field(default_factory=list)
    chapters: list[PublicationChapter] = Field(default_factory=list)
    figures: list[PublicationFigure] = Field(default_factory=list)
    tables: list[PublicationTable] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    references: list[ReferenceEntry] = Field(default_factory=list)
