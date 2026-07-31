"""Unit tests for quality gate and stage machine (design lock-in)."""

from backend.domain.enums import ProjectStage, ReviewDecision
from backend.domain.review import EditorialReview, TechnicalReview
from backend.orchestration.quality_gate import can_finalize, requires_manual_review
from backend.orchestration.state_machine import assert_transition, can_transition


def test_quality_gate_blocks_numeric_mismatch():
    tech = TechnicalReview(
        decision=ReviewDecision.REVISE,
        numeric_mismatch_count=1,
    )
    edit = EditorialReview(decision=ReviewDecision.PASS)
    assert can_finalize(tech, edit) is False


def test_quality_gate_passes_clean():
    tech = TechnicalReview(decision=ReviewDecision.PASS)
    edit = EditorialReview(decision=ReviewDecision.PASS)
    assert can_finalize(tech, edit) is True


def test_manual_after_max_revisions():
    tech = TechnicalReview(
        decision=ReviewDecision.REVISE,
        unsupported_claim_count=1,
    )
    edit = EditorialReview(decision=ReviewDecision.PASS)
    assert requires_manual_review(tech, edit, revision_count=3) is True


def test_outline_approval_to_producing():
    assert can_transition(
        ProjectStage.WAITING_FOR_OUTLINE_APPROVAL,
        ProjectStage.PRODUCING,
    )
    assert not can_transition(
        ProjectStage.WAITING_FOR_OUTLINE_APPROVAL,
        ProjectStage.EXPORTED,
    )


def test_illegal_transition_raises():
    try:
        assert_transition(ProjectStage.CREATED, ProjectStage.PRODUCING)
        assert False, "expected ValueError"
    except ValueError:
        pass
