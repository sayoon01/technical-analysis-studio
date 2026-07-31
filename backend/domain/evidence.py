"""Evidence and structured fact schemas.

사실 근거는 EVIDENCE_SOURCE에서만 온다.
수치·프로세스·아키텍처는 페이지·위치와 함께 저장한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.enums import (
    EvidenceType,
    MetricDirection,
    VerificationStatus,
)


class ContentBlock(BaseModel):
    block_id: str
    source_id: str
    page_number: int
    block_type: str
    text: str
    bbox: tuple[float, float, float, float]
    reading_order: int
    confidence: float = 0.0
    parent_section: str | None = None


class EvidenceItem(BaseModel):
    evidence_id: str
    type: EvidenceType
    statement: str
    source_id: str
    page: int
    block_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    entities: list[str] = Field(default_factory=list)


class MetricFact(BaseModel):
    metric_id: str
    name: str
    definition: str | None = None
    measurement_method: str | None = None
    baseline_value: float | None = None
    result_value: float | None = None
    change_value: float | None = None
    change_unit: str | None = None
    direction: MetricDirection | None = None
    source_id: str
    page_number: int
    confidence: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class ProcessStep(BaseModel):
    step_id: str
    order: int
    label: str
    actor: str | None = None
    description: str | None = None


class ProcessConnection(BaseModel):
    from_step_id: str
    to_step_id: str
    label: str | None = None


class ProcessFact(BaseModel):
    process_id: str
    title: str
    actors: list[str] = Field(default_factory=list)
    steps: list[ProcessStep] = Field(default_factory=list)
    connections: list[ProcessConnection] = Field(default_factory=list)
    source_id: str
    page_number: int


class ArchitectureNode(BaseModel):
    node_id: str
    label: str
    node_type: str | None = None
    group: str | None = None


class ArchitectureEdge(BaseModel):
    from_node_id: str
    to_node_id: str
    label: str | None = None
    medium: str | None = None


class ArchitectureFact(BaseModel):
    architecture_id: str
    nodes: list[ArchitectureNode] = Field(default_factory=list)
    edges: list[ArchitectureEdge] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    source_id: str
    page_number: int


class EvidenceConflict(BaseModel):
    conflict_id: str
    description: str
    evidence_ids: list[str]
    severity: str = "MAJOR"


class EvidencePack(BaseModel):
    section_id: str
    section_objective: str
    research_questions: list[str] = Field(default_factory=list)
    definitions: list[EvidenceItem] = Field(default_factory=list)
    supporting_facts: list[EvidenceItem] = Field(default_factory=list)
    metrics: list[MetricFact] = Field(default_factory=list)
    process_facts: list[ProcessFact] = Field(default_factory=list)
    architecture_facts: list[ArchitectureFact] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    previous_section_content: str | None = None
    reuse_decision: str | None = None
