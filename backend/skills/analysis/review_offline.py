"""Deterministic technical review against EvidencePack + citations."""

from __future__ import annotations

import re
import uuid

from backend.domain.enums import IssueSeverity, ReviewDecision
from backend.domain.evidence import EvidencePack
from backend.domain.review import ReviewIssue, TechnicalReview
from backend.skills.analysis.section_writer import extract_citations

_NUM_PCT = re.compile(
    r"(?P<sign>[+\-]?)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|퍼센트)"
)
_CITATION_RE = re.compile(r"\[[A-Za-z0-9\-]+,\s*p\.\d+\]")


def review_technical_offline(
    *,
    section_id: str,
    markdown: str,
    pack: EvidencePack,
    claims: list[dict] | None = None,
) -> TechnicalReview:
    issues: list[ReviewIssue] = []
    pack_pages = _pack_page_index(pack)
    pack_numbers = _pack_numbers(pack)

    cites = extract_citations(markdown)
    citation_mismatch = 0
    for c in cites:
        key = (c["source_id"], c["page"])
        if key not in pack_pages:
            citation_mismatch += 1
            issues.append(
                _issue(
                    section_id,
                    "CITATION_MISMATCH",
                    IssueSeverity.CRITICAL,
                    f"인용 {c['span']} 이 Evidence Pack에 없음",
                    "Pack에 있는 source/page로 인용을 고치거나 해당 문장을 삭제",
                )
            )

    unsupported = 0
    for claim in claims or []:
        if claim.get("claim_type") == "ANALYSIS":
            continue
        if claim.get("verification_status") == "UNVERIFIED" or claim.get(
            "claim_type"
        ) == "UNSUPPORTED":
            # Major if looks like a factual assertion with numbers or strong verbs
            stmt = claim.get("statement") or ""
            if _looks_major_claim(stmt):
                unsupported += 1
                issues.append(
                    _issue(
                        section_id,
                        "UNSUPPORTED_CLAIM",
                        IssueSeverity.CRITICAL,
                        f"근거 없는 주요 주장: {stmt[:120]}",
                        "Evidence Pack 근거를 붙이거나 주장을 삭제/약화",
                        paragraph_id=None,
                    )
                )

    # Bare factual sentences with numbers but no citation nearby
    for para in _paragraphs(markdown):
        if "【분석】" in para or para.startswith("<!--"):
            continue
        nums = list(_NUM_PCT.finditer(para))
        if not nums:
            continue
        local_cites = extract_citations(para)
        if not local_cites and _looks_major_claim(para):
            unsupported += 1
            issues.append(
                _issue(
                    section_id,
                    "UNSUPPORTED_CLAIM",
                    IssueSeverity.CRITICAL,
                    f"수치 주장에 인용 없음: {_clip(para, 100)}",
                    "Pack 근거 인용을 추가하거나 수치 문장 삭제",
                )
            )

    numeric_mismatch = 0
    md_for_nums = _CITATION_RE.sub("", markdown)
    for m in _NUM_PCT.finditer(md_for_nums):
        value = float(m.group("value"))
        unit = m.group("unit")
        # Only percentage-like figures are gate blockers (avoid page numbers etc.)
        if not unit:
            continue
        if value not in pack_numbers and not _approx_in(value, pack_numbers):
            if not _number_in_pack_text(value, pack):
                numeric_mismatch += 1
                issues.append(
                    _issue(
                        section_id,
                        "NUMERIC_MISMATCH",
                        IssueSeverity.CRITICAL,
                        f"Pack에 없는 수치 {m.group(0).strip()} 사용",
                        "Evidence Pack 수치만 사용하거나 해당 문장 삭제",
                    )
                )

    # Deduplicate numeric issues by value
    seen_num = set()
    deduped = []
    for iss in issues:
        if iss.issue_type == "NUMERIC_MISMATCH":
            if iss.description in seen_num:
                continue
            seen_num.add(iss.description)
            deduped.append(iss)
        else:
            deduped.append(iss)
    issues = deduped
    numeric_mismatch = sum(1 for i in issues if i.issue_type == "NUMERIC_MISMATCH")
    unsupported = sum(1 for i in issues if i.issue_type == "UNSUPPORTED_CLAIM")
    citation_mismatch = sum(1 for i in issues if i.issue_type == "CITATION_MISMATCH")

    critical = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
    covered = 0.0
    if claims:
        verified = sum(1 for c in claims if c.get("verification_status") == "VERIFIED")
        covered = verified / max(len(claims), 1)

    if critical > 0 or unsupported or citation_mismatch or numeric_mismatch:
        decision = ReviewDecision.REVISE
    else:
        decision = ReviewDecision.PASS

    return TechnicalReview(
        decision=decision,
        issues=issues,
        evidence_coverage=covered,
        unsupported_claim_count=unsupported,
        citation_mismatch_count=citation_mismatch,
        numeric_mismatch_count=numeric_mismatch,
        critical_issue_count=critical,
    )


def review_editorial_offline(
    *,
    section_id: str,
    markdown: str,
) -> "EditorialReview":
    from backend.domain.review import EditorialReview

    issues: list[ReviewIssue] = []
    promo_phrases = (
        "최고의",
        "혁신적인 솔루션",
        "완벽한",
        "업계 최고",
        "반드시 도입",
        "세계 최고",
    )
    promo = 0
    for p in promo_phrases:
        if p in markdown:
            promo += 1
            issues.append(
                _issue(
                    section_id,
                    "PROMOTIONAL_LANGUAGE",
                    IssueSeverity.MAJOR,
                    f"홍보성 표현: {p}",
                    "객관적 서술로 재작성",
                    reviewer_type="editorial",
                )
            )

    paras = [p for p in _paragraphs(markdown) if len(p) > 40]
    dup = 0
    for i, a in enumerate(paras):
        for b in paras[i + 1 :]:
            if _similarity(a, b) > 0.85:
                dup += 1
                issues.append(
                    _issue(
                        section_id,
                        "DUPLICATE_PARAGRAPH",
                        IssueSeverity.MINOR,
                        f"유사 문단 반복: {_clip(a, 60)}",
                        "중복 문단 통합",
                        reviewer_type="editorial",
                    )
                )
                break

    ratio = (dup / len(paras)) if paras else 0.0
    critical = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
    # Editorial major promo doesn't block finalize alone unless critical
    decision = ReviewDecision.PASS
    if critical or promo >= 2 or ratio > 0.1:
        decision = ReviewDecision.REVISE

    return EditorialReview(
        decision=decision,
        issues=issues,
        duplicate_paragraph_ratio=ratio,
        promotional_phrase_count=promo,
        terminology_inconsistency_count=0,
        critical_issue_count=critical,
    )


def _pack_page_index(pack: EvidencePack) -> set[tuple[str, int]]:
    pages: set[tuple[str, int]] = set()
    for item in list(pack.definitions) + list(pack.supporting_facts):
        pages.add((item.source_id, item.page))
    for m in pack.metrics:
        pages.add((m.source_id, m.page_number))
    return pages


def _pack_numbers(pack: EvidencePack) -> set[float]:
    nums: set[float] = set()
    for m in pack.metrics:
        if m.change_value is not None:
            nums.add(float(m.change_value))
        if m.baseline_value is not None:
            nums.add(float(m.baseline_value))
        if m.result_value is not None:
            nums.add(float(m.result_value))
    return nums


def _number_in_pack_text(value: float, pack: EvidencePack) -> bool:
    needle = str(int(value)) if value == int(value) else str(value)
    for item in list(pack.definitions) + list(pack.supporting_facts):
        if needle in item.statement:
            return True
    for m in pack.metrics:
        blob = f"{m.name} {m.measurement_method or ''} {m.definition or ''}"
        if needle in blob:
            return True
    return False


def _approx_in(value: float, nums: set[float], tol: float = 0.01) -> bool:
    return any(abs(value - n) <= tol for n in nums)


def _looks_major_claim(text: str) -> bool:
    if any(ch.isdigit() for ch in text):
        return True
    strong = ("증가", "감소", "향상", "입증", "보장", "반드시", "완벽하게", "원인이다")
    return any(s in text for s in strong)


def _paragraphs(md: str) -> list[str]:
    chunks = re.split(r"\n\s*\n", md)
    out = []
    for c in chunks:
        t = c.strip()
        if not t or t.startswith("#") or t.startswith("<!-- SECTION"):
            continue
        # strip para markers
        t = re.sub(r"<!--\s*P-[^>]+-->", "", t).strip()
        if t:
            out.append(t)
    return out


def _similarity(a: str, b: str) -> float:
    ta = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", a.lower()))
    tb = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _issue(
    section_id: str,
    issue_type: str,
    severity: IssueSeverity,
    description: str,
    recommendation: str,
    *,
    paragraph_id: str | None = None,
    reviewer_type: str = "technical",
) -> ReviewIssue:
    return ReviewIssue(
        issue_id=f"ISS-{uuid.uuid4().hex[:8].upper()}",
        section_id=section_id,
        reviewer_type=reviewer_type,
        severity=severity,
        issue_type=issue_type,
        paragraph_id=paragraph_id,
        description=description,
        recommendation=recommendation,
        status="OPEN",
    )


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"
