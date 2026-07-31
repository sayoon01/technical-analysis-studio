"""Impact analysis: which parent sections change when new evidence arrives."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from backend.domain.edition import SectionImpact
from backend.domain.enums import ClaimRelation, ImpactDecision
from backend.skills.retrieval.embedder import cosine, embed_text
from backend.storage.edition_repository import ClaimRepository, SectionRepository


@dataclass
class ImpactReport:
    parent_edition_id: str
    new_source_ids: list[str]
    section_impacts: list[SectionImpact] = field(default_factory=list)
    claim_relations: list[dict] = field(default_factory=list)

    def decisions_by_section(self) -> dict[str, ImpactDecision]:
        return {i.section_id: i.decision for i in self.section_impacts}


class ImpactAnalyzer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.sections = SectionRepository(conn)
        self.claims = ClaimRepository(conn)

    def analyze(
        self,
        *,
        parent_edition_id: str,
        new_source_ids: list[str],
        all_evidence_source_ids: list[str] | None = None,
    ) -> ImpactReport:
        report = ImpactReport(
            parent_edition_id=parent_edition_id,
            new_source_ids=list(new_source_ids),
        )
        if not new_source_ids:
            for sec in self.sections.list_for_edition(parent_edition_id):
                report.section_impacts.append(
                    SectionImpact(
                        section_id=sec["section_id"],
                        decision=ImpactDecision.KEEP,
                        reasons=["추가 Evidence Source 없음"],
                    )
                )
            return report

        new_chunks = self._load_source_texts(new_source_ids)
        new_metrics = self._load_metrics(new_source_ids)
        new_blob = "\n".join(c["text"] for c in new_chunks)
        new_vec = embed_text(new_blob[:4000]) if new_blob.strip() else None

        parent_sections = self.sections.list_for_edition(parent_edition_id)
        for sec in parent_sections:
            claims = self.claims.list_for_section(sec["section_id"])
            decision, reasons, affected, relations = self._decide_section(
                section=sec,
                claims=claims,
                new_chunks=new_chunks,
                new_metrics=new_metrics,
                new_vec=new_vec,
                all_evidence_source_ids=all_evidence_source_ids,
            )
            report.section_impacts.append(
                SectionImpact(
                    section_id=sec["section_id"],
                    decision=decision,
                    reasons=reasons,
                    affected_claim_ids=affected,
                )
            )
            report.claim_relations.extend(relations)

        return report

    def _decide_section(
        self,
        *,
        section: dict,
        claims: list[dict],
        new_chunks: list[dict],
        new_metrics: list[dict],
        new_vec: list[float] | None,
        all_evidence_source_ids: list[str] | None,
    ) -> tuple[ImpactDecision, list[str], list[str], list[dict]]:
        reasons: list[str] = []
        affected: list[str] = []
        relations: list[dict] = []
        title = section.get("title") or ""
        objective = section.get("objective") or ""
        body = section.get("content_markdown") or ""
        section_focus = f"{title}\n{objective}"

        # Unsupported inheritance risk: claims without evidence in corpus
        unsupported = [
            c
            for c in claims
            if c.get("verification_status") == "UNVERIFIED"
            or c.get("claim_type") == "UNSUPPORTED"
            or not (c.get("evidence") or c.get("evidence_ids"))
        ]
        # Also: major numeric claims in body not backed by any evidence source metric
        if unsupported:
            reasons.append(
                f"이전 Edition에 근거 부족 주장 {len(unsupported)}건 — 계승 시 제거/재검증 필요"
            )

        metric_hits = []
        for m in new_metrics:
            if _token_overlap(section_focus + "\n" + body, m.get("name") or "") >= 1:
                metric_hits.append(m)

        text_score = 0.0
        overlapping_chunks = 0
        for ch in new_chunks:
            ov = _token_overlap(section_focus, ch["text"])
            if ov >= 2:
                overlapping_chunks += 1
                text_score = max(text_score, ov / 10.0)
        if new_vec is not None and body.strip():
            sim = cosine(new_vec, embed_text(body[:4000]))
            text_score = max(text_score, float(sim))

        # Claim-level relations vs new metrics/text
        for c in claims:
            stmt = c.get("statement") or ""
            rel = None
            for m in new_metrics:
                if _token_overlap(stmt, m.get("name") or "") >= 1:
                    # same metric name with different value → CONTRADICTS/REPLACES
                    nums = _extract_pct_values(stmt)
                    mv = m.get("change_value")
                    if mv is not None and nums and float(mv) not in nums and not any(
                        abs(float(mv) - n) < 0.01 for n in nums
                    ):
                        rel = ClaimRelation.REPLACES
                    else:
                        rel = ClaimRelation.EXTENDS
                    break
            if rel is None and _token_overlap(stmt, "\n".join(ch["text"] for ch in new_chunks[:20])) >= 3:
                rel = ClaimRelation.SUPPORTS
            if rel:
                relations.append(
                    {
                        "claim_id": c["claim_id"],
                        "relation": rel.value,
                        "section_id": section["section_id"],
                    }
                )
                affected.append(c["claim_id"])

        if any(r["relation"] == ClaimRelation.REPLACES.value for r in relations):
            reasons.append("새 자료가 기존 수치/주장을 대체함")
            return ImpactDecision.FULL_REWRITE, reasons, affected, relations

        if metric_hits:
            reasons.append(
                "새 자료에 관련 정량 지표가 추가됨: "
                + ", ".join(m.get("name", "") for m in metric_hits[:3])
            )
            return ImpactDecision.PARTIAL_REWRITE, reasons, affected, relations

        if overlapping_chunks >= 2 or text_score >= 0.35:
            reasons.append("새 자료 텍스트가 장 주제와 유의하게 겹침")
            return ImpactDecision.PARTIAL_REWRITE, reasons, affected, relations

        if unsupported:
            # Keep structure but scrub unsupported
            reasons.append("내용은 유지하되 무근거 주장 제거")
            return ImpactDecision.LIGHT_EDIT, reasons, [c["claim_id"] for c in unsupported], relations

        if text_score >= 0.15 or overlapping_chunks == 1:
            reasons.append("인용만 보강 가능한 약한 연관")
            return ImpactDecision.UPDATE_CITATION, reasons, affected, relations

        reasons.append("새 자료와 직접 연관 없음")
        return ImpactDecision.KEEP, reasons, affected, relations

    def _load_source_texts(self, source_ids: list[str]) -> list[dict]:
        if not source_ids:
            return []
        ph = ",".join("?" * len(source_ids))
        rows = self.conn.execute(
            f"""
            SELECT source_id, page_number, text, block_id
            FROM content_blocks
            WHERE source_id IN ({ph}) AND block_type != 'IMAGE'
            ORDER BY page_number, reading_order
            """,
            source_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_metrics(self, source_ids: list[str]) -> list[dict]:
        if not source_ids:
            return []
        ph = ",".join("?" * len(source_ids))
        rows = self.conn.execute(
            f"SELECT * FROM metric_facts WHERE source_id IN ({ph})",
            source_ids,
        ).fetchall()
        return [dict(r) for r in rows]


def _token_overlap(a: str, b: str) -> int:
    ta = set(re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", (a or "").lower()))
    tb = set(re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", (b or "").lower()))
    return len(ta & tb)


def _extract_pct_values(text: str) -> set[float]:
    return {float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text or "")}
