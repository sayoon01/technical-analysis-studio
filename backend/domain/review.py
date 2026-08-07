"""Review and revision schemas.

Canonical ReviewIssue is the single Domain contract for reviewer / validator
findings. API/Persistence may map fields (e.g. description → message).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.enums import IssueSeverity, ReviewDecision


class ReviewIssue(BaseModel):
    issue_id: str
    section_id: str
    reviewer_type: str  # technical | editorial | validator
    severity: IssueSeverity
    issue_type: str
    paragraph_id: str | None = None
    description: str
    recommendation: str
    status: str = "OPEN"
    # Optional evidence refs when relevant (not exposed as new Frontend enum)
    evidence_refs: list[str] = Field(default_factory=list)


class TechnicalReview(BaseModel):
    decision: ReviewDecision
    issues: list[ReviewIssue] = Field(default_factory=list)
    evidence_coverage: float = 0.0
    unsupported_claim_count: int = 0
    citation_mismatch_count: int = 0
    numeric_mismatch_count: int = 0
    critical_issue_count: int = 0
    # online | offline (explicit mode) — never silent fallback
    provenance: str = "online"


class EditorialReview(BaseModel):
    decision: ReviewDecision
    issues: list[ReviewIssue] = Field(default_factory=list)
    duplicate_paragraph_ratio: float = 0.0
    promotional_phrase_count: int = 0
    terminology_inconsistency_count: int = 0
    critical_issue_count: int = 0
    provenance: str = "online"


class RevisionResult(BaseModel):
    revision: int
    updated_content: str
    changes: list[dict] = Field(default_factory=list)
    resolved_issue_ids: list[str] = Field(default_factory=list)
    provenance: str = "online"
