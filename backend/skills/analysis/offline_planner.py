"""Deterministic corpus-driven analysis/plan (offline / fallback).

Derives structure from what is present in the corpus — never from a fixed
domain template (MES/NPU/…).
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

from backend.domain.report_plan import (
    AnalysisQuestion,
    CorpusAnalysis,
    OutlineNode,
    QuantitativeFinding,
    ReportPlan,
)


def analyze_offline(context: dict) -> CorpusAnalysis:
    texts = [p.get("text") or "" for p in context.get("pages") or []]
    joined = "\n".join(texts)
    page_types = context.get("page_type_counts") or {}

    main_topic = _first_substantial_line(texts) or "기술자료 분석"
    domain = _guess_domain_label(joined)

    problems = _extract_lines_matching(
        joined,
        ("문제", "한계", "부족", "미연계", "누락", "노후", "장애", "위험", "challenge", "issue"),
    )
    components = _extract_lines_matching(
        joined,
        ("구성", "아키텍처", "서버", "클라우드", "모듈", "노드", "VPN", "PDA", "시스템"),
    )
    processes = _extract_lines_matching(
        joined,
        ("절차", "프로세스", "흐름", "단계", "주문", "생산", "출하", "공정", "workflow"),
    )
    qualitative = _extract_lines_matching(
        joined,
        ("안정", "확장", "보안", "효과", "개선", "향상"),
    )

    # Entities: capitalized / Hangul noun-ish tokens from titles
    entities = _top_terms(joined, n=12)
    techs = [t for t in entities if _looks_tech(t)][:8]

    qfindings: list[QuantitativeFinding] = []
    for m in context.get("metrics") or []:
        unit = m.get("change_unit") or ""
        change = None
        if m.get("change_value") is not None:
            change = f"{m['change_value']}{unit}"
        elif m.get("result_value") is not None:
            change = f"{m['result_value']}{unit}"
        qfindings.append(
            QuantitativeFinding(
                name=m["name"],
                change=change,
                change_value=m.get("change_value"),
                change_unit=m.get("change_unit"),
                direction=m.get("direction"),
                page_number=m.get("page_number"),
                source_id=m.get("source_id"),
                measurement_method=m.get("measurement_method"),
            )
        )

    gaps = []
    if page_types.get("DIAGRAM") and not components:
        gaps.append("다이어그램 페이지는 있으나 구성요소 텍스트 추출이 제한적임")
    if qfindings and not any(q.measurement_method for q in qfindings):
        gaps.append("일부 정량 지표의 측정방법이 불명확함")

    focus = []
    if problems:
        focus.append("문제 배경과 도입 필요성")
    if components or page_types.get("DIAGRAM"):
        focus.append("시스템/기술 구성")
    if processes:
        focus.append("업무 또는 기술 프로세스 변화")
    if qfindings:
        focus.append("정량 성과와 측정 조건")
    focus.append("자료 한계와 확인 불가 사항")

    return CorpusAnalysis(
        main_topic=main_topic[:120],
        technical_domain=domain,
        document_purpose="업로드 기술자료에 대한 전문가 기술분석",
        key_entities=entities[:10],
        key_technologies=techs,
        business_or_technical_problems=problems[:8],
        system_components=components[:8],
        processes=processes[:8],
        quantitative_findings=qfindings,
        qualitative_findings=qualitative[:6],
        evidence_gaps=gaps,
        contradictions=[],
        recommended_report_focus=focus,
    )


def plan_offline(analysis: CorpusAnalysis, source_ids: list[str] | None = None) -> ReportPlan:
    source_scope = source_ids or []
    nodes: list[OutlineNode] = []
    order = 0

    def add(
        title: str,
        objective: str,
        *,
        level: int = 1,
        parent_id: str | None = None,
        evidence: list[str] | None = None,
        visuals: list[str] | None = None,
        questions: list[str] | None = None,
        length: int = 800,
    ) -> OutlineNode:
        nonlocal order
        order += 1
        node = OutlineNode(
            node_id=f"N-{uuid.uuid4().hex[:8].upper()}",
            parent_id=parent_id,
            level=level,
            order=order,
            title=title,
            objective=objective,
            analysis_questions=questions or [],
            expected_length=length,
            source_scope=list(source_scope),
            required_evidence_types=evidence or [],
            planned_visuals=visuals or [],
        )
        nodes.append(node)
        return node

    add(
        "분석 개요",
        f"{analysis.main_topic}에 대한 분석 목적·범위·자료·제약을 정의한다.",
        evidence=["DEFINITION"],
        questions=[f"{analysis.main_topic}의 분석 범위는 무엇인가?"],
    )
    overview = nodes[-1]

    if analysis.business_or_technical_problems:
        parent = add(
            "문제와 배경",
            "자료에서 확인되는 기존 문제·추진 배경을 정리하고, 그 의미를 분석한다. 미확인은 한계로 명시한다.",
            evidence=["PROBLEM"],
            questions=["자료가 제시하는 핵심 문제는 무엇인가?"],
        )
        for i, prob in enumerate(analysis.business_or_technical_problems[:4], start=1):
            add(
                _short_title(prob, fallback=f"문제 {i}"),
                f"‘{prob}’에 대한 근거 있는 사실과 분석 포인트를 서술한다. 확인되지 않은 내용은 한계로 적는다.",
                level=2,
                parent_id=parent.node_id,
                evidence=["PROBLEM"],
                length=400,
            )

    if analysis.system_components or analysis.key_technologies:
        parent = add(
            "기술 구성과 주요 요소",
            "솔루션·시스템·핵심 기술 구성요소를 설명한다.",
            evidence=["ARCHITECTURE", "DEFINITION"],
            visuals=["ARCHITECTURE_DIAGRAM"] if analysis.system_components else [],
            questions=["핵심 구성요소와 역할은 무엇인가?"],
        )
        for i, comp in enumerate((analysis.system_components or analysis.key_technologies)[:4], 1):
            add(
                _short_title(comp, fallback=f"구성 {i}"),
                f"‘{comp}’의 역할·자료상 근거를 정리하고 기술적으로 해석한다. 미확인 세부 구현은 단정하지 않는다.",
                level=2,
                parent_id=parent.node_id,
                evidence=["ARCHITECTURE"],
                length=400,
            )

    if analysis.processes:
        parent = add(
            "프로세스와 변화",
            "업무/기술 흐름과 변경점을 사실과 분석으로 서술한다. 자료 공백은 한계로 명시한다.",
            evidence=["PROCESS", "COMPARISON"],
            visuals=["PROCESS_FLOW"],
            questions=["자료에 나타난 프로세스 단계는 무엇인가?"],
        )
        for i, proc in enumerate(analysis.processes[:4], 1):
            add(
                _short_title(proc, fallback=f"흐름 {i}"),
                f"‘{proc}’ 관련 절차의 사실과 변화 의미를 정리한다.",
                level=2,
                parent_id=parent.node_id,
                evidence=["PROCESS"],
                length=400,
            )

    if analysis.quantitative_findings:
        parent = add(
            "정량 성과",
            "측정된 지표·변화량·측정방법을 근거와 함께 기술하고, 성과 해석과 한계를 구분한다.",
            evidence=["METRIC"],
            visuals=["BAR_CHART", "COMPARISON_TABLE"],
            questions=["각 지표의 정의와 측정 조건은 무엇인가?"],
        )
        for i, m in enumerate(analysis.quantitative_findings[:6], 1):
            add(
                m.name[:40] or f"지표 {i}",
                f"{m.name}의 변화({m.change or 'N/A'})·측정 조건을 근거와 함께 서술하고 의미를 분석한다.",
                level=2,
                parent_id=parent.node_id,
                evidence=["METRIC"],
                length=350,
            )

    if analysis.qualitative_findings:
        add(
            "정성 효과와 조건",
            "정성 평가를 자료 근거 범위에서 정리하고, 해석과 한계를 명시한다.",
            evidence=["QUALITATIVE", "CONSTRAINT"],
        )

    add(
        "기술적 분석과 한계",
        "성공 요인·전제조건·자료만으로 확인하기 어려운 사항을 구분한다.",
        evidence=["CONSTRAINT"],
        questions=list(analysis.evidence_gaps[:3]) or ["자료의 분석 한계는 무엇인가?"],
    )
    add(
        "종합 결론",
        "앞 장의 근거에 기반한 결론과 시사점을 제시한다. 확인되지 않은 확정 주장은 피하고 한계를 남긴다.",
        evidence=["DEFINITION"],
        length=600,
    )

    questions = [
        AnalysisQuestion(
            question_id=f"Q-{i:02d}",
            question=q,
            related_evidence_types=[],
        )
        for i, q in enumerate(
            [
                f"{analysis.main_topic}의 핵심 분석 질문은 무엇인가?",
                *analysis.recommended_report_focus,
            ][:6],
            start=1,
        )
    ]

    title = f"{analysis.main_topic} 기술분석서"
    subtitle = None
    if analysis.recommended_report_focus:
        subtitle = " · ".join(analysis.recommended_report_focus[:2])

    return ReportPlan(
        title=title[:160],
        subtitle=subtitle,
        purpose=analysis.document_purpose or "기술자료 기반 전문가 분석",
        target_reader="기술·기획 의사결정자",
        report_summary=(
            f"{analysis.main_topic} ({analysis.technical_domain}). "
            f"초점: {', '.join(analysis.recommended_report_focus[:3])}"
        ),
        analysis_questions=questions,
        outline=nodes,
        terminology_policy={},
        expected_visuals=[],
        evidence_gaps=list(analysis.evidence_gaps),
    )


def _first_substantial_line(texts: list[str]) -> str | None:
    for t in texts:
        for line in t.splitlines():
            s = line.strip()
            if len(s) >= 8:
                return s
    return None


def _guess_domain_label(text: str) -> str:
    # Soft label from frequent tech-ish tokens — not a fixed taxonomy branch.
    terms = _top_terms(text, n=5)
    return " / ".join(terms[:3]) if terms else "general-technical"


def _extract_lines_matching(text: str, keywords: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip(" •-\t")
        if len(s) < 4 or len(s) > 80:
            continue
        if any(k.lower() in s.lower() for k in keywords):
            key = re.sub(r"\s+", " ", s)
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _top_terms(text: str, n: int = 10) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-_/]{1,}|[가-힣]{2,}", text)
    stop = {
        "그리고",
        "또는",
        "위한",
        "대한",
        "있는",
        "없는",
        "통해",
        "관련",
        "기반",
        "기존",
        "구축",
        "페이지",
        "소개",
        "개요",
        "the",
        "and",
        "for",
        "with",
    }
    counts = Counter(t for t in tokens if t.lower() not in stop and len(t) > 1)
    return [w for w, _ in counts.most_common(n)]


def _looks_tech(term: str) -> bool:
    if re.search(r"[A-Za-z]", term) and len(term) <= 24:
        return True
    tech_kr = ("시스템", "클라우드", "서버", "네트워크", "데이터", "공정", "모델", "센서")
    return any(k in term for k in tech_kr)


def _short_title(text: str, fallback: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= 40:
        return t or fallback
    return t[:37] + "..."
