"""Project and source domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.domain.enums import PageType, ProjectStage, SourceRole, SourceStatus


class Project(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    stage: ProjectStage = ProjectStage.CREATED
    current_edition_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Source(BaseModel):
    source_id: str
    project_id: str
    filename: str
    mime_type: str | None = None
    role: SourceRole = SourceRole.EVIDENCE_SOURCE
    status: SourceStatus = SourceStatus.UPLOADED
    page_count: int | None = None
    storage_path: str | None = None
    ocr_quality: float | None = None
    created_at: datetime | None = None


class SourcePage(BaseModel):
    page_id: str
    source_id: str
    page_number: int
    page_type: PageType = PageType.TEXT
    text_layer_available: bool = True
    image_path: str | None = None
    width: float | None = None
    height: float | None = None


class CorpusSnapshot(BaseModel):
    snapshot_id: str
    project_id: str
    snapshot_number: int
    source_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
