"""Evidence refine delta merge — provenance fields stay code-owned."""

from backend.domain.enums import EvidenceType
from backend.domain.evidence import (
    EvidenceItem,
    EvidencePack,
    EvidenceRefineDelta,
    MetricFact,
)
from backend.skills.retrieval.evidence_refine import apply_evidence_refine_delta


def _pack() -> EvidencePack:
    return EvidencePack(
        section_id="SEC-TEST",
        section_objective="obj",
        definitions=[
            EvidenceItem(
                evidence_id="EV-A",
                type=EvidenceType.DEFINITION,
                statement="def a",
                source_id="SRC-1",
                page=1,
            )
        ],
        supporting_facts=[
            EvidenceItem(
                evidence_id="EV-B",
                    type=EvidenceType.QUALITATIVE,
                    statement="fact b",
                    source_id="SRC-1",
                    page=2,
                ),
                EvidenceItem(
                    evidence_id="EV-C",
                    type=EvidenceType.COMPARISON,
                statement="fact c",
                source_id="SRC-2",
                page=3,
            ),
        ],
        metrics=[
            MetricFact(
                metric_id="MET-1",
                name="재공재고",
                change_value=-33.0,
                change_unit="%",
                source_id="SRC-1",
                page_number=10,
            )
        ],
    )


def test_delta_rank_and_drop_preserves_provenance():
    pack = _pack()
    out = apply_evidence_refine_delta(
        pack,
        EvidenceRefineDelta(
            keep_ids=["EV-C", "EV-A", "MET-1"],
            drop_ids=["EV-B"],
            ranking=["MET-1", "EV-C", "EV-A"],
            missing_evidence=["실험 환경 미기재"],
        ),
    )
    assert [e.evidence_id for e in out.definitions] == ["EV-A"]
    assert [e.evidence_id for e in out.supporting_facts] == ["EV-C"]
    assert out.metrics[0].metric_id == "MET-1"
    assert out.metrics[0].source_id == "SRC-1"
    assert out.metrics[0].page_number == 10
    assert "실험 환경 미기재" in out.missing_evidence


def test_unknown_ids_ignored_empty_keep_falls_back():
    pack = _pack()
    out = apply_evidence_refine_delta(
        pack,
        EvidenceRefineDelta(keep_ids=["EV-NOPE"], drop_ids=["EV-B"]),
    )
    # keep invalid → treated like empty keep with drops applied via selected=known-drop
    # Actually: keep_raw empty after filter, drop has EV-B → selected = known - drop
    ids = {e.evidence_id for e in out.definitions + out.supporting_facts}
    assert "EV-B" not in ids
    assert "EV-A" in ids
    assert out.metrics[0].page_number == 10
