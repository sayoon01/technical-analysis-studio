"""Deterministic quality gate. LLM scores are advisory only."""

from __future__ import annotations

from backend.domain.review import EditorialReview, TechnicalReview
from backend.skills.analysis.draft_validator import DraftValidationResult


def can_finalize(
    technical: TechnicalReview,
    editorial: EditorialReview,
    *,
    unrendered_visual_count: int = 0,
    draft_validation: DraftValidationResult | None = None,
) -> bool:
    """Blockers must all be zero. Soft LLM scores are ignored."""
    if draft_validation is not None and not draft_validation.ok:
        return False
    return (
        technical.unsupported_claim_count == 0
        and technical.citation_mismatch_count == 0
        and technical.numeric_mismatch_count == 0
        and technical.critical_issue_count == 0
        and editorial.critical_issue_count == 0
        and unrendered_visual_count == 0
    )


def requires_manual_review(
    technical: TechnicalReview,
    editorial: EditorialReview,
    revision_count: int,
    max_revisions: int = 3,
) -> bool:
    if revision_count >= max_revisions and not can_finalize(technical, editorial):
        return True
    return (
        technical.decision.value == "MANUAL_REVIEW"
        or editorial.decision.value == "MANUAL_REVIEW"
    )
