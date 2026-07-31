"""Report edition and claim schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.domain.enums import EditionStatus, ImpactDecision


class ReportEdition(BaseModel):
    edition_id: str
    project_id: str
    edition_number: int
    parent_edition_id: str | None = None
    corpus_snapshot_id: str
    report_plan_id: str
    outline_id: str
    status: EditionStatus = EditionStatus.DRAFT
    created_at: datetime | None = None


class Claim(BaseModel):
    claim_id: str
    edition_id: str
    section_id: str
    statement: str
    claim_type: str
    importance: str
    evidence_ids: list[str] = Field(default_factory=list)
    verification_status: str = "UNVERIFIED"


class SectionImpact(BaseModel):
    section_id: str
    decision: ImpactDecision
    reasons: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
