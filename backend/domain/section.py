"""Section domain model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Section(BaseModel):
    section_id: str
    edition_id: str
    outline_node_id: str
    title: str
    objective: str
    content_markdown: str = ""
    status: str = "PENDING"
    revision_count: int = 0
    evidence_pack_id: str | None = None
    updated_at: datetime | None = None


class SectionVersion(BaseModel):
    version_id: str
    section_id: str
    revision: int
    content_markdown: str
    change_summary: str | None = None
    created_at: datetime | None = None
    claim_ids: list[str] = Field(default_factory=list)
