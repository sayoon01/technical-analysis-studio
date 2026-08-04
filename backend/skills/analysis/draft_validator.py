"""Deterministic draft validator — runs before LLM reviewers."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field

from backend.domain.chapter import ChapterDraft
from backend.domain.enums import IssueSeverity
from backend.domain.evidence import EvidencePack
from backend.domain.review import ReviewIssue

_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_PARA_MARKER_RE = re.compile(r"P-(?:INFRA|PROB|ARCH|RES|SUM)-\d+", re.I)
_VISUAL_REQ_RE = re.compile(r"VISUAL_REQUEST", re.I)
_FORBIDDEN = (
    "<!--",
    "P-INFRA-",
    "P-PROB-",
    "VISUAL_REQUEST",
)


class DraftValidationResult(BaseModel):
    ok: bool = True
    issues: list[ReviewIssue] = Field(default_factory=list)
    internal_marker_count: int = 0
    empty_paragraph_count: int = 0
    missing_evidence_id_count: int = 0
    forbidden_string_count: int = 0


def validate_draft(
    *,
    section_id: str,
    markdown: str,
    pack: EvidencePack,
    draft: ChapterDraft | None = None,
) -> DraftValidationResult:
    """Code-level checks that must pass before (or alongside) LLM review."""
    issues: list[ReviewIssue] = []
    marker_count = 0
    empty_count = 0
    missing_eid = 0
    forbidden_count = 0

    comments = _HTML_COMMENT_RE.findall(markdown or "")
    if comments:
        marker_count += len(comments)
        forbidden_count += len(comments)
        issues.append(
            _issue(
                section_id,
                "INTERNAL_MARKER",
                IssueSeverity.CRITICAL,
                f"본문에 HTML 주석 {len(comments)}개 포함",
                "내부 마커를 제거하고 구조화 paragraph_id만 DB에 유지",
            )
        )
    if _PARA_MARKER_RE.search(markdown or ""):
        marker_count += 1
        forbidden_count += 1
        issues.append(
            _issue(
                section_id,
                "INTERNAL_MARKER",
                IssueSeverity.CRITICAL,
                "본문에 P-INFRA/P-PROB 등 내부 단락 마커가 노출됨",
                "마커를 삭제하고 사용자용 문장만 남김",
            )
        )
    if _VISUAL_REQ_RE.search(markdown or ""):
        marker_count += 1
        forbidden_count += 1
        issues.append(
            _issue(
                section_id,
                "INTERNAL_MARKER",
                IssueSeverity.CRITICAL,
                "본문에 VISUAL_REQUEST 문자열이 노출됨",
                "VisualIntent로 분리하고 본문에서는 제거",
            )
        )

    for token in _FORBIDDEN:
        # already covered above for most; catch residual SRC-/EVD- exposure in body
        pass

    # Do not expose raw evidence ids as body tokens like EVD-...
    if re.search(r"\bEVD-[A-Za-z0-9]+\b", markdown or ""):
        forbidden_count += 1
        issues.append(
            _issue(
                section_id,
                "FORBIDDEN_STRING",
                IssueSeverity.MAJOR,
                "본문에 원본 evidence_id(EVD-...)가 노출됨",
                "인용은 [SRC-..., p.N] 형식만 사용",
            )
        )

    pack_eids = _pack_evidence_ids(pack)

    if draft is not None:
        for sub in draft.subsections:
            for para in sub.paragraphs:
                text = (para.text or "").strip()
                if not text:
                    empty_count += 1
                    issues.append(
                        _issue(
                            section_id,
                            "EMPTY_PARAGRAPH",
                            IssueSeverity.MAJOR,
                            f"빈 문단: {para.paragraph_id}",
                            "빈 문단을 삭제하거나 근거 있는 문장으로 채움",
                            paragraph_id=para.paragraph_id,
                        )
                    )
                if _HTML_COMMENT_RE.search(text) or _PARA_MARKER_RE.search(text):
                    marker_count += 1
                    issues.append(
                        _issue(
                            section_id,
                            "INTERNAL_MARKER",
                            IssueSeverity.CRITICAL,
                            f"문단 {para.paragraph_id}에 내부 마커 포함",
                            "문단 텍스트에서 마커 제거",
                            paragraph_id=para.paragraph_id,
                        )
                    )
                for eid in para.evidence_ids:
                    if eid not in pack_eids:
                        missing_eid += 1
                        issues.append(
                            _issue(
                                section_id,
                                "MISSING_EVIDENCE_ID",
                                IssueSeverity.CRITICAL,
                                f"문단 {para.paragraph_id}의 evidence_id {eid} 가 Pack에 없음",
                                "Pack에 있는 evidence_id만 연결",
                                paragraph_id=para.paragraph_id,
                            )
                        )
        for intent in draft.visual_intents:
            if not (intent.visual_type or "").strip() or not (intent.purpose or "").strip():
                issues.append(
                    _issue(
                        section_id,
                        "INVALID_VISUAL_INTENT",
                        IssueSeverity.MAJOR,
                        "VisualIntent에 visual_type/purpose가 비어 있음",
                        "형식에 맞게 VisualIntent를 채우거나 제거",
                    )
                )
            for eid in intent.related_evidence_ids:
                if eid not in pack_eids:
                    missing_eid += 1
                    issues.append(
                        _issue(
                            section_id,
                            "MISSING_EVIDENCE_ID",
                            IssueSeverity.MAJOR,
                            f"VisualIntent 관련 evidence_id {eid} 가 Pack에 없음",
                            "Pack evidence만 연결하거나 intent 제거",
                        )
                    )
    else:
        # Markdown-only empty paragraph heuristic
        chunks = [c.strip() for c in re.split(r"\n\s*\n", markdown or "") if c.strip()]
        for c in chunks:
            if c in {"", ".", "…"}:
                empty_count += 1

    critical = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
    major = sum(1 for i in issues if i.severity == IssueSeverity.MAJOR)
    ok = critical == 0 and major == 0 and marker_count == 0 and missing_eid == 0

    return DraftValidationResult(
        ok=ok,
        issues=issues,
        internal_marker_count=marker_count,
        empty_paragraph_count=empty_count,
        missing_evidence_id_count=missing_eid,
        forbidden_string_count=forbidden_count,
    )


def _pack_evidence_ids(pack: EvidencePack) -> set[str]:
    ids: set[str] = set()
    for item in list(pack.definitions) + list(pack.supporting_facts):
        ids.add(item.evidence_id)
    for m in pack.metrics:
        ids.add(m.metric_id)
    return ids


def _issue(
    section_id: str,
    issue_type: str,
    severity: IssueSeverity,
    description: str,
    recommendation: str,
    *,
    paragraph_id: str | None = None,
) -> ReviewIssue:
    return ReviewIssue(
        issue_id=f"ISS-{uuid.uuid4().hex[:8].upper()}",
        section_id=section_id,
        reviewer_type="deterministic",
        severity=severity,
        issue_type=issue_type,
        paragraph_id=paragraph_id,
        description=description,
        recommendation=recommendation,
        status="OPEN",
    )
