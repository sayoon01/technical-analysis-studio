"""Visual request schema. Rendering is deterministic code, not an agent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.enums import VisualType


class VisualRequest(BaseModel):
    visual_id: str
    section_id: str
    visual_type: VisualType
    title: str
    purpose: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    render_spec: dict = Field(default_factory=dict)
