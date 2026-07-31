"""Claim extraction from written section markdown + evidence linking."""

from __future__ import annotations

import re
import uuid

from backend.domain.edition import Claim
from backend.domain.evidence import EvidencePack
from backend.skills.analysis.section_writer import extract_citations

_PARA_RE = re.compile(r"<!--\s*(P-[A-Za-z0-9\-]+)\s*-->\s*\n?(?P<body>.*?)(?=\n<!--|\n#|\Z)", re.S)


def extract_claims(
    *,
    edition_id: str,
    section_id: str,
    markdown: str,
    pack: EvidencePack,
) -> list[tuple[Claim, list[str]]]:
    """Return list of (Claim, evidence_ids)."""
    evidence_index = _index_pack(pack)
    results: list[tuple[Claim, list[str]]] = []

    paras = list(_PARA_RE.finditer(markdown))
    if not paras:
        # fallback: whole doc citations
        cites = extract_citations(markdown)
        if cites:
            eids = _match_evidence(cites, evidence_index)
            claim = Claim(
                claim_id=f"CLM-{uuid.uuid4().hex[:10].upper()}",
                edition_id=edition_id,
                section_id=section_id,
                statement=_clip(markdown, 300),
                claim_type="GENERAL",
                importance="MAJOR" if eids else "MINOR",
                evidence_ids=eids,
                verification_status="VERIFIED" if eids else "UNVERIFIED",
            )
            results.append((claim, eids))
        return results

    for m in paras:
        body = (m.group("body") or "").strip()
        if not body or body.startswith("【분석】"):
            # Analysis paragraphs: still record but mark as ANALYSIS
            if body.startswith("【분석】"):
                claim = Claim(
                    claim_id=f"CLM-{uuid.uuid4().hex[:10].upper()}",
                    edition_id=edition_id,
                    section_id=section_id,
                    statement=_clip(body, 400),
                    claim_type="ANALYSIS",
                    importance="MINOR",
                    evidence_ids=[],
                    verification_status="ANALYSIS",
                )
                results.append((claim, []))
            continue

        cites = extract_citations(body)
        eids = _match_evidence(cites, evidence_index)
        statement = _CITATION_STRIP.sub("", body).strip()
        if len(statement) < 8:
            continue
        claim = Claim(
            claim_id=f"CLM-{uuid.uuid4().hex[:10].upper()}",
            edition_id=edition_id,
            section_id=section_id,
            statement=_clip(statement, 400),
            claim_type="FACT" if cites else "UNSUPPORTED",
            importance="MAJOR" if cites else "MINOR",
            evidence_ids=eids,
            verification_status="VERIFIED" if eids else "UNVERIFIED",
        )
        results.append((claim, eids))
    return results


_CITATION_STRIP = re.compile(r"\s*\[[A-Za-z0-9\-]+,\s*p\.\d+\]")


def _index_pack(pack: EvidencePack) -> dict[tuple[str, int], list[str]]:
    idx: dict[tuple[str, int], list[str]] = {}
    for item in list(pack.definitions) + list(pack.supporting_facts):
        idx.setdefault((item.source_id, item.page), []).append(item.evidence_id)
    for m in pack.metrics:
        idx.setdefault((m.source_id, m.page_number), []).append(m.metric_id)
    return idx


def _match_evidence(
    cites: list[dict], index: dict[tuple[str, int], list[str]]
) -> list[str]:
    eids: list[str] = []
    for c in cites:
        key = (c["source_id"], c["page"])
        for eid in index.get(key, []):
            if eid not in eids:
                eids.append(eid)
    return eids


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"
