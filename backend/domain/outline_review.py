"""Outline review models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.enums import IssueSeverity, ReviewDecision


class OutlineIssue(BaseModel):
    issue_id: str
    severity: IssueSeverity
    issue_type: str
    node_id: str | None = None
    description: str
    recommendation: str | None = None


class OutlineReview(BaseModel):
    decision: ReviewDecision
    issues: list[OutlineIssue] = Field(default_factory=list)
    summary: str | None = None
