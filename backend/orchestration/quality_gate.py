"""Deterministic quality gate. LLM scores are advisory only.

Canonical owner of PASS / REVISE / MANUAL_REVIEW branching input.
Reviewers emit issues; ReviewLoop executes branches.
"""

from __future__ import annotations

from backend.domain.enums import IssueSeverity, ReviewDecision
from backend.domain.review import EditorialReview, TechnicalReview
from backend.orchestration.issue_aggregator import AggregatedReview, aggregate_issues
from backend.skills.analysis.draft_validator import DraftValidationResult

_BLOCKING = {IssueSeverity.CRITICAL, IssueSeverity.MAJOR}


def can_finalize(
    technical: TechnicalReview,
    editorial: EditorialReview,
    *,
    unrendered_visual_count: int = 0,
    draft_validation: DraftValidationResult | None = None,
    aggregated: AggregatedReview | None = None,
) -> bool:
    """Blockers must all be zero. Soft LLM scores are ignored."""
    if aggregated is not None:
        if aggregated.blocking_issue_count > 0:
            return False
        if draft_validation is None:
            draft_validation = aggregated.draft_validation
        technical = aggregated.technical
        editorial = aggregated.editorial
    if draft_validation is not None and not draft_validation.ok:
        return False
    if any(i.severity in _BLOCKING for i in technical.issues):
        return False
    if any(i.severity in _BLOCKING for i in editorial.issues):
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
    *,
    draft_validation: DraftValidationResult | None = None,
    aggregated: AggregatedReview | None = None,
) -> bool:
    if revision_count >= max_revisions and not can_finalize(
        technical,
        editorial,
        draft_validation=draft_validation,
        aggregated=aggregated,
    ):
        return True
    return (
        technical.decision == ReviewDecision.MANUAL_REVIEW
        or editorial.decision == ReviewDecision.MANUAL_REVIEW
    )


def decide_gate(
    *,
    technical: TechnicalReview,
    editorial: EditorialReview,
    revision_count: int,
    max_revisions: int,
    draft_validation: DraftValidationResult | None = None,
    unrendered_visual_count: int = 0,
    aggregated: AggregatedReview | None = None,
) -> ReviewDecision:
    """Single Quality Gate decision. Never silent-PASS on blockers."""
    agg = aggregated or aggregate_issues(
        technical=technical,
        editorial=editorial,
        draft_validation=draft_validation,
    )
    if can_finalize(
        technical,
        editorial,
        unrendered_visual_count=unrendered_visual_count,
        draft_validation=draft_validation,
        aggregated=agg,
    ):
        return ReviewDecision.PASS
    if requires_manual_review(
        technical,
        editorial,
        revision_count,
        max_revisions,
        draft_validation=draft_validation,
        aggregated=agg,
    ):
        return ReviewDecision.MANUAL_REVIEW
    return ReviewDecision.REVISE
