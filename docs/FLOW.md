# 최종 실행 흐름

```text
[사용자] 원본 업로드
    ↓
[Ingestion Skills] 텍스트/OCR/레이아웃/표/수치/다이어그램 + bbox
    ↓
[CorpusAnalyst] 주제·문제·기술·구조·성과·공백
    ↓
[ReportPlanner] 제목·질문·동적 목차·장 목표
    ↓
[사용자] 목차 수정·승인  ← WAITING_FOR_OUTLINE_APPROVAL
    ↓
[EvidenceResearcher] 장별 Evidence Pack (원본만)
    ↓
[TechnicalWriter] 장 초안
    ↓
[TechnicalReviewer ∥ EditorialReviewer]
    ↓
[Quality Gate] 실패 → Reviser (≤3) → 재검토 / 통과
    ↓
[Visual renderers] 표·차트·Mermaid·Graphviz
    ↓
[Finalization] 용어·중복·인용·결론 정합
    ↓
[Export] MD / DOCX / PDF / ZIP → Edition V1
    ↓
추가 자료 + Parent Edition
    ↓
[ImpactAnalyzer] 영향 장만 KEEP/REWRITE
    ↓
Edition V2
```

중심은 Writer가 아니라: **정확히 읽기 → 근거 구조화 → 분석 논리 → 원문 대조 → 안전 계승**.
