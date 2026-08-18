"""ADK structured outputs for analyze vertical slice."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceIntelligenceOutput(BaseModel):
    main_topic: str
    technical_domain: str
    document_purpose: str | None = None
    key_entities: list[str] = Field(default_factory=list)
    key_technologies: list[str] = Field(default_factory=list)
    business_or_technical_problems: list[str] = Field(default_factory=list)
    system_components: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    qualitative_findings: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    recommended_report_focus: list[str] = Field(default_factory=list)


class EvidenceDecisionItem(BaseModel):
    evidence_id: str
    status: str  # accepted | rejected | failed
    reason: str | None = None


class EvidenceDecisionOutput(BaseModel):
    decisions: list[EvidenceDecisionItem] = Field(default_factory=list)
    accepted_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
