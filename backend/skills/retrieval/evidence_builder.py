"""Build EvidencePack from hybrid retrieval + structured facts (deterministic)."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path

from backend.domain.enums import EvidenceType, MetricDirection, VerificationStatus
from backend.domain.evidence import (
    ArchitectureEdge,
    ArchitectureFact,
    ArchitectureNode,
    EvidenceItem,
    EvidencePack,
    MetricFact,
    ProcessConnection,
    ProcessFact,
    ProcessStep,
)
from backend.skills.retrieval.hybrid_search import hybrid_search


def build_evidence_pack(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    section_id: str,
    section_objective: str,
    title: str,
    research_questions: list[str] | None = None,
    required_evidence_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    evidence_top_k: int = 10,
    vector_root: Path | None = None,
) -> EvidencePack:
    questions = list(research_questions or [])
    if not questions:
        questions = [f"{title}: {section_objective}"]

    queries = [title, section_objective, *questions[:4]]
    hits: list[dict] = []
    seen_keys: set[str] = set()
    for q in queries:
        q = (q or "").strip()
        if len(q) < 2:
            continue
        for row in hybrid_search(
            conn,
            project_id,
            q,
            source_ids=source_ids,
            merged_top_k=evidence_top_k,
            vector_root=vector_root,
        ):
            key = (
                f"{row.get('source_id')}:{row.get('page_number')}:"
                f"{(row.get('text') or '')[:60]}"
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            hits.append(row)

    supporting: list[EvidenceItem] = []
    definitions: list[EvidenceItem] = []
    for row in hits[:evidence_top_k]:
        text = (row.get("text") or "").strip()
        if not text or text == "[IMAGE]":
            continue
        sid = row.get("source_id") or ""
        page = int(row.get("page_number") or 0)
        etype = _classify_evidence_type(text, title, required_evidence_types)
        item = EvidenceItem(
            evidence_id=f"EV-{uuid.uuid4().hex[:10].upper()}",
            type=etype,
            statement=_clip(text, 400),
            source_id=sid,
            page=page,
            block_ids=list(row.get("block_ids") or ([row["block_id"]] if row.get("block_id") else [])),
            confidence=float(row.get("rank_score") or row.get("score") or 0.5),
        )
        if etype == EvidenceType.DEFINITION:
            definitions.append(item)
        else:
            supporting.append(item)

    metrics = _load_relevant_metrics(
        conn,
        source_ids=source_ids,
        title=title,
        objective=section_objective,
        required=required_evidence_types,
    )
    process_facts, architecture_facts = _load_structure_facts(
        conn,
        source_ids=source_ids,
        title=title,
        objective=section_objective,
        required=required_evidence_types,
    )

    missing: list[str] = []
    req = {t.upper() for t in (required_evidence_types or [])}
    if "METRIC" in req and not metrics:
        missing.append("정량 지표 근거가 부족함")
    if "ARCHITECTURE" in req and not architecture_facts and not any(
        i.type == EvidenceType.ARCHITECTURE for i in supporting
    ):
        missing.append("아키텍처 근거가 부족함")
    if "PROCESS" in req and not process_facts and not any(
        i.type == EvidenceType.PROCESS for i in supporting
    ):
        missing.append("프로세스 근거가 부족함")
    if not supporting and not metrics and not process_facts and not architecture_facts:
        missing.append("관련 원문 근거를 충분히 찾지 못함")

    limitations = []
    if missing:
        limitations.append("Evidence Pack에 없는 세부 사실은 단정하지 말 것")
    for af in architecture_facts:
        if not af.edges:
            limitations.append(
                f"p{af.page_number} 구성도: 노드 그룹은 확인했으나 연결선 미검증"
            )
    for pf in process_facts:
        if not pf.connections:
            limitations.append(
                f"p{pf.page_number} 흐름도: 단계 목록은 있으나 화살표 연결 미검증"
            )

    return EvidencePack(
        section_id=section_id,
        section_objective=section_objective,
        research_questions=questions,
        definitions=definitions,
        supporting_facts=supporting,
        metrics=metrics,
        process_facts=process_facts,
        architecture_facts=architecture_facts,
        conflicts=[],
        limitations=limitations,
        missing_evidence=missing,
    )


def _classify_evidence_type(
    text: str,
    title: str,
    required: list[str] | None,
) -> EvidenceType:
    blob = f"{title}\n{text}".lower()
    if any(k in blob for k in ("%","증가", "감소", "향상", "지표")):
        return EvidenceType.METRIC
    if any(k in blob for k in ("구성", "아키텍처", "vpn", "클라우드", "노드", "연결")):
        return EvidenceType.ARCHITECTURE
    if any(k in blob for k in ("절차", "프로세스", "흐름", "단계", "주문", "출하")):
        return EvidenceType.PROCESS
    if any(k in blob for k in ("문제", "한계", "누락", "미연계", "노후")):
        return EvidenceType.PROBLEM
    if any(k in blob for k in ("정의", "이란", "의미", "측정방법")):
        return EvidenceType.DEFINITION
    if required:
        try:
            return EvidenceType(required[0].upper())
        except ValueError:
            pass
    return EvidenceType.QUALITATIVE


def _load_relevant_metrics(
    conn: sqlite3.Connection,
    *,
    source_ids: list[str] | None,
    title: str,
    objective: str,
    required: list[str] | None,
) -> list[MetricFact]:
    if source_ids is None:
        rows = conn.execute("SELECT * FROM metric_facts").fetchall()
    elif not source_ids:
        return []
    else:
        ph = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"SELECT * FROM metric_facts WHERE source_id IN ({ph})",
            source_ids,
        ).fetchall()

    want_metrics = required is None or any(
        t.upper() == "METRIC" for t in (required or [])
    ) or any(k in f"{title}{objective}" for k in ("성과", "지표", "정량", "효과", "생산", "클레임", "납기", "온도", "효율"))

    out: list[MetricFact] = []
    for r in rows:
        name = r["name"] or ""
        overlap = _token_overlap(f"{title} {objective}", name)
        if not want_metrics and overlap < 1:
            continue
        if want_metrics and overlap < 1 and len(rows) > 6:
            if (r["confidence"] or 0) < 0.7:
                continue
        direction = None
        if r["direction"]:
            try:
                direction = MetricDirection(r["direction"])
            except ValueError:
                direction = None
        status = VerificationStatus.UNVERIFIED
        if r["verification_status"]:
            try:
                status = VerificationStatus(r["verification_status"])
            except ValueError:
                pass
        out.append(
            MetricFact(
                metric_id=r["metric_id"],
                name=name,
                definition=r["definition"],
                measurement_method=r["measurement_method"],
                baseline_value=r["baseline_value"],
                result_value=r["result_value"],
                change_value=r["change_value"],
                change_unit=r["change_unit"],
                direction=direction,
                source_id=r["source_id"],
                page_number=r["page_number"],
                confidence=float(r["confidence"] or 0),
                verification_status=status,
            )
        )
    return out[:8]


def _load_structure_facts(
    conn: sqlite3.Connection,
    *,
    source_ids: list[str] | None,
    title: str,
    objective: str,
    required: list[str] | None,
) -> tuple[list[ProcessFact], list[ArchitectureFact]]:
    try:
        if source_ids is None:
            rows = conn.execute("SELECT * FROM structure_facts").fetchall()
        elif not source_ids:
            return [], []
        else:
            ph = ",".join("?" * len(source_ids))
            rows = conn.execute(
                f"SELECT * FROM structure_facts WHERE source_id IN ({ph})",
                source_ids,
            ).fetchall()
    except sqlite3.OperationalError:
        return [], []

    blob = f"{title} {objective}"
    want_proc = required is None or any(
        t.upper() == "PROCESS" for t in (required or [])
    ) or any(k in blob for k in ("프로세스", "흐름", "절차", "업무"))
    want_arch = required is None or any(
        t.upper() == "ARCHITECTURE" for t in (required or [])
    ) or any(k in blob for k in ("구성", "아키텍처", "시스템", "인프라"))

    processes: list[ProcessFact] = []
    architectures: list[ArchitectureFact] = []
    for r in rows:
        kind = (r["fact_kind"] or "").upper()
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        overlap = _token_overlap(blob, r["title"] or "") + _token_overlap(
            blob, " ".join(n.get("label", "") for n in (payload.get("nodes") or [])[:8])
        )
        if kind == "PROCESS" and (want_proc or overlap >= 1):
            processes.append(_to_process_fact(r, payload))
        elif kind == "ARCHITECTURE" and (want_arch or overlap >= 1):
            architectures.append(_to_architecture_fact(r, payload))
    return processes[:4], architectures[:4]


def _to_process_fact(row, payload: dict) -> ProcessFact:
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    steps = [
        ProcessStep(
            step_id=str(n.get("node_id") or f"S{i}"),
            order=i,
            label=str(n.get("label") or ""),
            actor=str(n["group"]) if n.get("group") else None,
        )
        for i, n in enumerate(nodes)
        if n.get("label")
    ]
    id_set = {s.step_id for s in steps}
    connections = [
        ProcessConnection(
            from_step_id=str(e.get("from_node_id") or e.get("from") or ""),
            to_step_id=str(e.get("to_node_id") or e.get("to") or ""),
            label=e.get("label") or e.get("medium"),
        )
        for e in edges
        if str(e.get("from_node_id") or e.get("from") or "") in id_set
        and str(e.get("to_node_id") or e.get("to") or "") in id_set
    ]
    return ProcessFact(
        process_id=row["fact_id"],
        title=row["title"] or "프로세스",
        actors=list({s.actor for s in steps if s.actor}),
        steps=steps,
        connections=connections,
        source_id=row["source_id"],
        page_number=int(row["page_number"]),
    )


def _to_architecture_fact(row, payload: dict) -> ArchitectureFact:
    nodes = [
        ArchitectureNode(
            node_id=str(n.get("node_id") or f"N{i}"),
            label=str(n.get("label") or ""),
            node_type=n.get("node_type"),
            group=n.get("group"),
        )
        for i, n in enumerate(payload.get("nodes") or [])
        if n.get("label")
    ]
    id_set = {n.node_id for n in nodes}
    edges = [
        ArchitectureEdge(
            from_node_id=str(e.get("from_node_id") or e.get("from") or ""),
            to_node_id=str(e.get("to_node_id") or e.get("to") or ""),
            label=e.get("label"),
            medium=e.get("medium"),
        )
        for e in (payload.get("edges") or [])
        if str(e.get("from_node_id") or e.get("from") or "") in id_set
        and str(e.get("to_node_id") or e.get("to") or "") in id_set
    ]
    return ArchitectureFact(
        architecture_id=row["fact_id"],
        nodes=nodes,
        edges=edges,
        groups=list(payload.get("groups") or []),
        source_id=row["source_id"],
        page_number=int(row["page_number"]),
    )


def _token_overlap(a: str, b: str) -> int:
    ta = set(re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", a.lower()))
    tb = set(re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", b.lower()))
    return len(ta & tb)


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"
