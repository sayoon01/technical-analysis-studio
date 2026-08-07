# 최종 실행 흐름

> Source of Truth: 현재 Runtime (`backend/orchestration/*`) + [AGENTS.md](../AGENTS.md) Final Architecture Decision.  
> 구설계의 ReportOrchestrator / EvidenceResearcher / TechnicalWriter stub / Reviewer 병렬은 **최종 Architecture가 아님**.

```text
[사용자] 원본 업로드
    ↓
[Ingestion Skills] 텍스트/OCR/레이아웃/표·수치·다이어그램 + bbox
    ↓
[SourcePipeline] ContentBlock / Evidence construction (deterministic)
    ↓
[CorpusAnalyst = Source Intelligence] 주제·문제·기술·구조·성과·공백
    ↓
[ReportStrategist] 목적·독자·범위·분량·작성 원칙
    ↓
[OutlineArchitect] 제목·동적 목차·장 목표
    (OutlineDesigner/ReportPlanner 중복은 단일 Owner로 통합)
    ↓
[OutlineReviewer] + deterministic Planning Gate
    ↓
[사용자] 목차 승인  ← WAITING_FOR_OUTLINE_APPROVAL
    ↓
CHAPTER LOOP (순차, 한 Chapter씩):
  Context Builder
    ↓
  Evidence Pack (deterministic retrieval; Writer에 원본 전체 비공개)
    ↓
  ChapterWriter 초안
    ↓
  Draft Validator
    ↓
  TechnicalReviewer
    ↓
  EditorialReviewer          ← 병렬 금지, 순차
    ↓
  Issue Aggregator → Quality Gate
    ↓
  실패 시 Reviser (targeted, 횟수 제한) → 필요 시 Reviewer 재검토
    ↓
  Final Chapter → 다음 Chapter
    ↓
[VisualService] 표·차트·Mermaid/Graphviz 등 deterministic 렌더
  (Visual Planner Agent는 기본 범위 아님)
    ↓
[Full Report Review / Finalization]
    ↓
[Export] MD / DOCX / PDF / ZIP → Edition
    ↓
추가 자료 + Parent Edition
    ↓
[ImpactAnalyzer] 영향 장만 KEEP/REWRITE
    ↓
다음 Edition
```

Persistence Canonical: v1 `sections` / `section_versions` / `reviews.section_id`.  
Domain의 Chapter 개념은 API·DB의 Section으로 매핑한다. `migrations_v2` chapters는 Retirement 대상.

중심은 Writer가 아니라: **정확히 읽기 → 근거 구조화 → 분석 논리 → 원문 대조 → 안전 계승**.
