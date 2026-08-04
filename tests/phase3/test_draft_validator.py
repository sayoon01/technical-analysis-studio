from __future__ import annotations

from backend.domain.chapter import ChapterDraft, DraftParagraph, SubsectionDraft, VisualIntent
from backend.domain.evidence import EvidenceItem, EvidencePack, EvidenceType
from backend.orchestration.quality_gate import can_finalize
from backend.domain.review import EditorialReview, ReviewDecision, TechnicalReview
from backend.skills.analysis.draft_validator import validate_draft
from backend.skills.analysis.revise_offline import revise_section_offline


def _pack() -> EvidencePack:
    return EvidencePack(
        section_id="SEC-1",
        section_objective="o",
        supporting_facts=[
            EvidenceItem(
                evidence_id="EV-1",
                type=EvidenceType.QUALITATIVE,
                statement="시간당 생산량 8% 증가",
                source_id="SRC-1",
                page=16,
            )
        ],
    )


def test_draft_validator_flags_internal_markers():
    md = "## 장\n\n<!-- P-INFRA-01 --> 본문 VISUAL_REQUEST: CHART\n"
    result = validate_draft(section_id="SEC-1", markdown=md, pack=_pack())
    assert not result.ok
    assert result.internal_marker_count >= 1
    types = {i.issue_type for i in result.issues}
    assert "INTERNAL_MARKER" in types


def test_draft_validator_checks_paragraph_evidence_ids():
    draft = ChapterDraft(
        chapter_id="CH-1",
        title="t",
        lead="l",
        subsections=[
            SubsectionDraft(
                subsection_id="SUB-1",
                title="s",
                paragraphs=[
                    DraftParagraph(
                        paragraph_id="PAR-1",
                        paragraph_type="FACT",
                        text="문장",
                        evidence_ids=["EV-MISSING"],
                    )
                ],
            )
        ],
        visual_intents=[
            VisualIntent(visual_type="TABLE", purpose="요약", related_evidence_ids=["EV-1"])
        ],
    )
    result = validate_draft(
        section_id="SEC-1",
        markdown="문장",
        pack=_pack(),
        draft=draft,
    )
    assert not result.ok
    assert result.missing_evidence_id_count >= 1


def test_quality_gate_blocks_on_draft_validation():
    tech = TechnicalReview(decision=ReviewDecision.PASS)
    ed = EditorialReview(decision=ReviewDecision.PASS)
    bad = validate_draft(
        section_id="SEC-1",
        markdown="<!-- marker -->",
        pack=_pack(),
    )
    assert not can_finalize(tech, ed, draft_validation=bad)


def test_reviser_strips_internal_markers():
    md = "<!-- P-INFRA-01 --> 시간당 생산량 8% 증가 [SRC-1, p.16]\n"
    tech = TechnicalReview(
        decision=ReviewDecision.REVISE,
        issues=[],
        critical_issue_count=1,
    )
    # force via deterministic style issue through offline strip always runs
    revised = revise_section_offline(
        title="성과",
        objective="성과",
        markdown=md,
        pack=_pack(),
        technical=tech,
        editorial=EditorialReview(decision=ReviewDecision.PASS),
        revision=2,
    )
    assert "<!--" not in revised.updated_content
    assert "P-INFRA-" not in revised.updated_content
