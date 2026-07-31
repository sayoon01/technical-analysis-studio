"""Offline / fallback technical writing from EvidencePack only."""

from __future__ import annotations

import re

from backend.domain.evidence import EvidencePack


def write_section_offline(
    *,
    title: str,
    objective: str,
    pack: EvidencePack,
    heading_level: int = 2,
) -> str:
    hashes = "#" * max(1, min(heading_level, 4))
    lines: list[str] = [f"{hashes} {title}", ""]
    lines.append(f"<!-- SECTION_OBJECTIVE: {objective} -->")
    lines.append("")

    para_idx = 0

    def para(text: str, citation: str | None = None) -> None:
        nonlocal para_idx
        para_idx += 1
        pid = f"P-{pack.section_id[-6:]}-{para_idx:02d}"
        cite = f" {citation}" if citation else ""
        lines.append(f"<!-- {pid} -->")
        lines.append(f"{text.rstrip()}{cite}")
        lines.append("")

    para(
        f"본 절은 ‘{objective}’을(를) 목표로 한다. "
        "사실·수치는 업로드 원본 근거만 쓰고, 해석·시사점·한계는 분석으로 구분해 서술한다."
    )

    if pack.definitions:
        for item in pack.definitions[:3]:
            cite = _cite(item.source_id, item.page)
            para(item.statement, cite)

    if pack.supporting_facts:
        lines.append(f"{hashes}# 확인된 사실")
        lines.append("")
        for item in pack.supporting_facts[:6]:
            cite = _cite(item.source_id, item.page)
            # Fact sentence
            para(item.statement, cite)

    if pack.metrics:
        lines.append(f"{hashes}# 정량 지표")
        lines.append("")
        for m in pack.metrics:
            change = ""
            unit = m.change_unit or ""
            if m.change_value is not None:
                direction = ""
                if m.direction:
                    direction = {
                        "INCREASE": "증가",
                        "DECREASE": "감소",
                        "UNCHANGED": "유지",
                    }.get(m.direction.value, m.direction.value)
                change = f" {m.change_value}{unit} {direction}".rstrip()
            elif m.result_value is not None:
                change = f" {m.result_value}{unit}"
            method = ""
            if m.measurement_method:
                method = f" 측정방법: {m.measurement_method}."
            cite = _cite(m.source_id, m.page_number)
            para(f"{m.name}{change}.{method}", cite)

    if pack.limitations or pack.missing_evidence:
        lines.append(f"{hashes}# 분석상 한계")
        lines.append("")
        for gap in (pack.missing_evidence or [])[:4]:
            para(f"자료에서 확인되지 않음: {gap}")
        for lim in (pack.limitations or [])[:3]:
            para(lim)

    if not pack.supporting_facts and not pack.metrics and not pack.definitions:
        para(
            "이 절과 직접 연결되는 원문 근거가 Evidence Pack에 충분하지 않다. "
            "세부 사실은 단정하지 않고, 확인 가능한 범위와 한계만 명시한다."
        )

    # Light analysis sentence (explicitly marked)
    if pack.supporting_facts or pack.metrics:
        para(
            "【분석】 위 사실에 근거해 기술·운영 함의를 해석한다. "
            "자료에 없는 수치·구현 세부·확정적 인과는 단정하지 않는다."
        )

    return "\n".join(lines).strip() + "\n"


def _cite(source_id: str, page: int) -> str:
    # Keep source_id as stored (already SRC-... or similar)
    sid = source_id
    return f"[{sid}, p.{page}]"


_CITATION_RE = re.compile(
    r"\[(?P<sid>[A-Za-z0-9\-]+),\s*p\.(?P<page>\d+)\]"
)


def extract_citations(markdown: str) -> list[dict]:
    return [
        {"source_id": m.group("sid"), "page": int(m.group("page")), "span": m.group(0)}
        for m in _CITATION_RE.finditer(markdown)
    ]
