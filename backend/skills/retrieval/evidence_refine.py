"""Apply LLM evidence refine deltas onto a code-built EvidencePack.

The LLM must never rewrite evidence_id / metric_id / source_id / page fields.
It only selects, drops, ranks, and notes gaps — code merges into the original pack.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from backend.domain.evidence import (
    ArchitectureFact,
    EvidenceConflict,
    EvidenceItem,
    EvidencePack,
    EvidenceRefineDelta,
    MetricFact,
    ProcessFact,
)


def apply_evidence_refine_delta(
    pack: EvidencePack,
    delta: EvidenceRefineDelta,
) -> EvidencePack:
    """Return a new pack with ranking/drops applied; provenance fields preserved."""
    evidence_pool = list(pack.definitions) + list(pack.supporting_facts)
    by_ev = {e.evidence_id: e for e in evidence_pool}
    by_metric = {m.metric_id: m for m in pack.metrics}
    by_process = {p.process_id: p for p in pack.process_facts}
    by_arch = {a.architecture_id: a for a in pack.architecture_facts}
    known = set(by_ev) | set(by_metric) | set(by_process) | set(by_arch)

    drop = {i for i in delta.drop_ids if i in known}
    keep_raw = [i for i in delta.keep_ids if i in known and i not in drop]
    ranking = [i for i in delta.ranking if i in known and i not in drop]

    if keep_raw:
        selected = set(keep_raw)
    elif drop:
        selected = known - drop
    else:
        selected = known

    # Ranking first, then remaining keep order (definitions then facts then metrics…)
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for i in ranking + keep_raw + list(_default_order(pack)):
        if i in selected and i not in seen:
            ordered_ids.append(i)
            seen.add(i)

    if not ordered_ids:
        # Empty keep / everything dropped → keep original order (quality enhancement only)
        return pack.model_copy(
            update={
                "missing_evidence": _merge_missing(
                    pack.missing_evidence, delta.missing_evidence
                ),
            }
        )

    definitions: list[EvidenceItem] = []
    supporting: list[EvidenceItem] = []
    metrics: list[MetricFact] = []
    processes: list[ProcessFact] = []
    architectures: list[ArchitectureFact] = []

    def_ids = {e.evidence_id for e in pack.definitions}
    for eid in ordered_ids:
        if eid in by_ev:
            item = by_ev[eid]
            if eid in def_ids:
                definitions.append(item)
            else:
                supporting.append(item)
        elif eid in by_metric:
            metrics.append(by_metric[eid])
        elif eid in by_process:
            processes.append(by_process[eid])
        elif eid in by_arch:
            architectures.append(by_arch[eid])

    conflicts = list(pack.conflicts)
    for hint in delta.conflicts:
        ids = [i for i in hint.evidence_ids if i in known]
        if not hint.description.strip():
            continue
        conflicts.append(
            EvidenceConflict(
                conflict_id=f"CF-{uuid.uuid4().hex[:8].upper()}",
                description=hint.description.strip(),
                evidence_ids=ids,
                severity="MAJOR",
            )
        )

    return pack.model_copy(
        update={
            "definitions": definitions,
            "supporting_facts": supporting,
            "metrics": metrics,
            "process_facts": processes,
            "architecture_facts": architectures,
            "conflicts": conflicts,
            "missing_evidence": _merge_missing(
                pack.missing_evidence, delta.missing_evidence
            ),
            "limitations": list(pack.limitations),
        }
    )


def evidence_catalog_for_llm(pack: EvidencePack) -> list[dict]:
    """Compact ID catalog — no full statements dump of the whole pack tree."""
    out: list[dict] = []
    for e in pack.definitions:
        out.append(
            {
                "id": e.evidence_id,
                "kind": "definition",
                "statement": (e.statement or "")[:180],
                "source_id": e.source_id,
                "page": e.page,
            }
        )
    for e in pack.supporting_facts:
        out.append(
            {
                "id": e.evidence_id,
                "kind": "supporting_fact",
                "statement": (e.statement or "")[:180],
                "source_id": e.source_id,
                "page": e.page,
            }
        )
    for m in pack.metrics:
        out.append(
            {
                "id": m.metric_id,
                "kind": "metric",
                "name": m.name,
                "source_id": m.source_id,
                "page": m.page_number,
            }
        )
    for p in pack.process_facts:
        out.append(
            {
                "id": p.process_id,
                "kind": "process",
                "title": p.title,
                "source_id": p.source_id,
                "page": p.page_number,
            }
        )
    for a in pack.architecture_facts:
        out.append(
            {
                "id": a.architecture_id,
                "kind": "architecture",
                "source_id": a.source_id,
                "page": a.page_number,
            }
        )
    return out


def _default_order(pack: EvidencePack) -> Iterable[str]:
    for e in pack.definitions:
        yield e.evidence_id
    for e in pack.supporting_facts:
        yield e.evidence_id
    for m in pack.metrics:
        yield m.metric_id
    for p in pack.process_facts:
        yield p.process_id
    for a in pack.architecture_facts:
        yield a.architecture_id


def _merge_missing(base: list[str], extra: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in list(base) + list(extra):
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:12]
