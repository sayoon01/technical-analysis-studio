"""Deterministic Issue Aggregator — no LLM.

Normalizes Technical + Editorial + DraftValidator issues into one decision input.
Does not invent new technical judgments.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.enums import IssueSeverity, ReviewDecision
from backend.domain.review import EditorialReview, ReviewIssue, TechnicalReview
from backend.skills.analysis.draft_validator import DraftValidationResult

_BLOCKING = {IssueSeverity.CRITICAL, IssueSeverity.MAJOR}
_VALIDATOR_TYPES = frozenset({"validator", "deterministic"})


class AggregatedReview(BaseModel):
    """Normalized review input for QualityGate / Reviser."""

    issues: list[ReviewIssue] = Field(default_factory=list)
    technical: TechnicalReview
    editorial: EditorialReview
    draft_validation: DraftValidationResult | None = None
    blocking_issue_count: int = 0
    critical_issue_count: int = 0
    major_issue_count: int = 0
    # Which semantic reviewers should re-run after a revision (deterministic).
    rereview_technical: bool = True
    rereview_editorial: bool = True


def aggregate_issues(
    *,
    technical: TechnicalReview,
    editorial: EditorialReview,
    draft_validation: DraftValidationResult | None = None,
) -> AggregatedReview:
    """Merge issues; preserve reviewer_type; dedupe exact duplicates."""
    raw: list[ReviewIssue] = []
    if draft_validation is not None:
        for iss in draft_validation.issues:
            # Normalize legacy "deterministic" label to validator
            if iss.reviewer_type in _VALIDATOR_TYPES:
                raw.append(iss.model_copy(update={"reviewer_type": "validator"}))
            else:
                raw.append(iss)
    raw.extend(list(technical.issues))
    raw.extend(list(editorial.issues))

    merged = _dedupe(raw)
    critical = sum(1 for i in merged if i.severity == IssueSeverity.CRITICAL)
    major = sum(1 for i in merged if i.severity == IssueSeverity.MAJOR)
    blocking = sum(1 for i in merged if i.severity in _BLOCKING)

    # Severity ordering: CRITICAL → MAJOR → MINOR
    order = {IssueSeverity.CRITICAL: 0, IssueSeverity.MAJOR: 1, IssueSeverity.MINOR: 2}
    merged.sort(key=lambda i: (order.get(i.severity, 9), i.reviewer_type, i.issue_type))

    need_tech, need_edit = _rereview_flags(merged)

    # Keep reviewer result objects intact (do not merge validator into technical).
    return AggregatedReview(
        issues=merged,
        technical=technical,
        editorial=editorial,
        draft_validation=draft_validation,
        blocking_issue_count=blocking,
        critical_issue_count=critical,
        major_issue_count=major,
        rereview_technical=need_tech,
        rereview_editorial=need_edit,
    )


def _dedupe(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[ReviewIssue] = []
    for iss in issues:
        key = (
            iss.reviewer_type,
            iss.issue_type,
            iss.severity.value if hasattr(iss.severity, "value") else str(iss.severity),
            (iss.description or "").strip()[:160],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(iss)
    return out


def _rereview_flags(issues: list[ReviewIssue]) -> tuple[bool, bool]:
    """Deterministic relevant-reviewer selection from open issue sources."""
    if not issues:
        return False, False
    need_tech = False
    need_edit = False
    for iss in issues:
        rt = (iss.reviewer_type or "").lower()
        if rt in {"technical", "validator", "deterministic"}:
            need_tech = True
        elif rt == "editorial":
            need_edit = True
        else:
            # Unknown source → re-run both (safe default, still sequential)
            need_tech = True
            need_edit = True
    # Validator structural issues also warrant technical pass after revise
    if any(i.reviewer_type == "validator" for i in issues):
        need_tech = True
    return need_tech, need_edit


def has_blocking_decision(technical: TechnicalReview, editorial: EditorialReview) -> bool:
    return (
        technical.decision != ReviewDecision.PASS
        or editorial.decision != ReviewDecision.PASS
    )
