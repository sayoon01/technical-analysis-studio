"""Corpus analysis and report planning schemas.

목차·제목은 자료에서 도출한다. 주제별 고정 템플릿을 두지 않는다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.domain.visual import VisualRequest


class PreviousEditionAnalysis(BaseModel):
    outline_fitness: str
    well_written_sections: list[str] = Field(default_factory=list)
    unsupported_statements: list[str] = Field(default_factory=list)
    sections_affected_by_new_sources: list[str] = Field(default_factory=list)
    sections_to_rewrite: list[str] = Field(default_factory=list)
    sections_to_keep: list[str] = Field(default_factory=list)


class QuantitativeFinding(BaseModel):
    """LLM/분석용 경량 수치 요약. DB MetricFact와 별개."""

    name: str
    change: str | None = None
    change_value: float | None = None
    change_unit: str | None = None
    direction: str | None = None
    page_number: int | None = None
    source_id: str | None = None
    measurement_method: str | None = None


def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, list):
        out: list[str] = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                out.append(item.strip())
            else:
                out.append(str(item))
        return [x for x in out if x]
    return [str(v)]


def _as_findings(v: Any) -> list[Any]:
    """Gemma often returns findings as plain strings — coerce to objects."""
    if v is None:
        return []
    if isinstance(v, str):
        return [{"name": v[:160], "change": v}] if v.strip() else []
    if not isinstance(v, list):
        return []
    out: list[Any] = []
    for item in v:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip()[:160], "change": item.strip()})
        elif isinstance(item, dict):
            row = dict(item)
            if not row.get("name") and row.get("change"):
                row["name"] = str(row["change"])[:160]
            if row.get("name"):
                out.append(row)
    return out


class CorpusAnalysis(BaseModel):
    main_topic: str
    technical_domain: str
    document_purpose: str | None = None
    key_entities: list[str] = Field(default_factory=list)
    key_technologies: list[str] = Field(default_factory=list)
    business_or_technical_problems: list[str] = Field(default_factory=list)
    system_components: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    quantitative_findings: list[QuantitativeFinding] = Field(default_factory=list)
    qualitative_findings: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    recommended_report_focus: list[str] = Field(default_factory=list)
    previous_edition_analysis: PreviousEditionAnalysis | None = None

    @field_validator(
        "key_entities",
        "key_technologies",
        "business_or_technical_problems",
        "system_components",
        "processes",
        "qualitative_findings",
        "evidence_gaps",
        "contradictions",
        "recommended_report_focus",
        mode="before",
    )
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _as_str_list(v)

    @field_validator("quantitative_findings", mode="before")
    @classmethod
    def _coerce_findings(cls, v: Any) -> list[Any]:
        return _as_findings(v)


class AnalysisQuestion(BaseModel):
    question_id: str
    question: str
    rationale: str | None = None
    related_evidence_types: list[str] = Field(default_factory=list)


class OutlineNode(BaseModel):
    node_id: str
    parent_id: str | None = None
    level: int
    order: int
    title: str
    objective: str
    analysis_questions: list[str] = Field(default_factory=list)
    expected_length: int = 0
    source_scope: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)
    planned_visuals: list[str] = Field(default_factory=list)


class ReportPlan(BaseModel):
    title: str
    subtitle: str | None = None
    purpose: str
    target_reader: str
    report_summary: str
    analysis_questions: list[AnalysisQuestion] = Field(default_factory=list)
    outline: list[OutlineNode] = Field(default_factory=list)
    terminology_policy: dict[str, str] = Field(default_factory=dict)
    expected_visuals: list[VisualRequest] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
