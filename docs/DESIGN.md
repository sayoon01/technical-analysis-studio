# Technical Analysis Studio — 최종 설계

> Ollama agents + deterministic skills 기반 전문가 기술분석서 생성 시스템  
> Book Studio와 무관한 **신규 프로젝트**. 코드·DB·Artifact·UI 재사용 없음.

## 1. 해결 문제

PDF·PPT·DOCX·HWP·XLSX 등 기술자료를 **텍스트뿐 아니라 표·수치·업무 흐름도·시스템 구성도까지** 분석한 뒤, 자료에 맞는 제목·목차를 자동 설계하고, 사용자 승인 후 전문가 수준 기술분석서를 작성·검토·개선·내보낸다.

### 핵심 제약

| 원칙 | 설명 |
|------|------|
| 도메인 비의존 | 주제·목차·지표 유형을 코드에 하드코딩하지 않음 |
| 원본만 사실 근거 | 이전 Edition은 수정 기반일 뿐, 새 사실의 근거가 아님 |
| 외부 검색 없음 | 사용자가 업로드한 자료만 사용 |
| LLM ≠ 파싱 | 파싱·OCR·레이아웃·렌더링·품질 게이트는 deterministic 코드 |

### 왜 단순 OCR 요약이 아닌가

발표자료형 PDF는 한 문서에 TEXT / DIAGRAM / MIXED / CHART가 섞인다.

- 흐름도·구성도: **그림 안 관계**가 핵심
- 비교 레이아웃: 텍스트 추출 시 **항목–설명 순서 뒤섞임** 가능
- 성과 지표: 수치뿐 아니라 **정의·측정방법**까지 구조화 필요

```
PDF → 페이지 유형 판별 → 원시 텍스트 → 페이지 이미지 → 레이아웃
   → 필요 시 OCR → 표·차트·다이어그램 분석 → 수치·조건·관계 구조화
   → 원문 페이지·bbox 연결
```

---

## 2. 운영 모델

### 2.1 두 작업

1. **신규 생성**: Sources A+B+C → Edition V1  
2. **개선**: Sources A+B+C+D + Parent Edition V1 → Edition V2 (이후 V3…)

### 2.2 근거 / 수정 / 형식 분리

| 역할 | SourceRole | 용도 |
|------|------------|------|
| 사실 근거 | `EVIDENCE_SOURCE` | 업로드 원본 기술자료만 |
| 수정 기반 | `PREVIOUS_EDITION` (업로드) / parent Edition | 업로드본은 문체·구조 참고만. 실제 개선 기반은 parent Edition |
| 형식 참고 | `FORMAT_REFERENCE` | 분석서 양식 (사실 근거 아님) |

이전 Edition의 오류가 V2/V3로 증폭되지 않도록 Evidence 검색과 이전 본문 검색을 **분리**한다.

---

## 3. 핵심 개념

```
Project                    # 분석 주제 최상위 단위
├── Sources                # 업로드 원본
├── Corpus Snapshots       # Edition 작성에 쓴 원본 묶음
└── Report Editions        # V1, V2, V3…
    ├── parent_edition
    ├── corpus_snapshot
    ├── report_plan / outline
    ├── sections (+ versions, claims, reviews)
    ├── visuals
    └── exports
```

---

## 4. 아키텍처

```
React/Vite UI
    │ REST
FastAPI Backend
    ├── Application Services (Project, Source, Plan, Edition, Review, …)
    └── ReportOrchestrator (stage facade)
            └── 7 LLM Agents (Ollama)
Deterministic Skills (Parser, OCR, Layout, Retrieval, Chart, Export)
Storage: SQLite + FTS5 + Vector Index + Files
```

### Agents vs Skills

| Agents (Ollama) | Skills (Python) |
|-----------------|-----------------|
| 분석·목차·근거정제·작성·검토·수정 | 문서 파싱·OCR·레이아웃 |
| structured JSON 생성 | 청크·임베딩·검색·DB |
| | 품질 게이트·렌더링·Export |

---

## 5. Agent (7개만)

```
ReportOrchestrator (stage-driven facade)
├── CorpusAnalystAgent
├── ReportPlannerAgent
├── EvidenceResearcherAgent
├── TechnicalWriterAgent
├── TechnicalReviewerAgent   ┐ 병렬
├── EditorialReviewerAgent   ┘
└── ReviserAgent
```

Visual Agent는 두지 않는다. Planner/Writer가 `VisualRequest`를 만들고 렌더링은 코드가 담당한다.

### ProjectStage

`CREATED → INGESTING → ANALYZING → PLANNING → WAITING_FOR_OUTLINE_APPROVAL → PRODUCING → REVIEWING → REVISING → FINALIZING → READY_FOR_EXPORT → EXPORTED`  
(+ `PAUSED`, `FAILED`)

목차 승인 전에는 본문 작성을 시작하지 않는다.

### Orchestrator 책임

단계 확인, Agent 실행, 입력 조립, 스키마 검증, DB/Artifact 저장, 목차 승인 대기, 장별 실행, Reviewer 병렬, 수정 횟수, 재시도·재개, Edition 생성.  
전체 순서를 LLM에 맡기지 않는다.

---

## 6. Agent별 입출력 요지

### CorpusAnalyst

파싱 결과를 받아 **의미** 분석. 주제·문제·구성·흐름·성과·충돌·근거 공백.  
이전 Edition이 있으면 유지/재작성 장도 분석.

→ `CorpusAnalysis`

### ReportPlanner

고정 템플릿 복사가 아님.  
분석 관점(필요성·문제·구성·흐름·변화·측정·한계·결론)을 검토하되 **모든 항목을 목차로 강제하지 않음**.

→ `ReportPlan` + `OutlineNode[]`

### EvidenceResearcher

장 목표 → 조사 질문 → Hybrid Retrieval(원본만) → `EvidencePack`  
Writer에게 원본 전체를 열어주지 않는다.

### TechnicalWriter

Plan + Outline + Evidence Pack + 문체/인용 정책 + 앞·뒤 장 맥락 + (선택) 이전 장.  
Evidence에 없는 핵심 사실 금지. 수치에 출처 페이지. 사실/분석 구분. 미확인은 명시.

### Reviewers (병렬)

- Technical: 근거·인용·수치·과장·이전 Edition 단독 근거
- Editorial: 구조·중복·문체·홍보문구·용어·시각자료 설명

### Reviser

지적 부분만 수정. 장 전체 재생성 금지. 최대 3회.

---

## 7. 품질 게이트 (코드 판정)

LLM 점수는 참고. 아래가 blocker:

- unsupported major claims = 0  
- broken citations = 0  
- numeric mismatches = 0  
- unresolved critical issues = 0  
- unrendered visual requests = 0  

`max_revisions: 3`, 초과 시 `MANUAL_REVIEW`.

---

## 8. Ingestion & Evidence 구조

### PageType

`TEXT | TABLE | CHART | DIAGRAM | IMAGE | MIXED | SCANNED`

OCR은 텍스트 레이어가 없거나 깨질 때만. 다이어그램·표 중심 페이지는 이미지 분석 필수.

### 구조화 Fact

- `ContentBlock` — bbox, reading_order (원문 하이라이트용)
- `MetricFact` — 정의·측정방법·baseline/result/change + verification_status
- `ProcessFact` — actors, steps, connections
- `ArchitectureFact` — nodes, edges, groups

### Hybrid Retrieval

FTS5 top-k ∪ Vector top-k → 병합·중복제거 → **EVIDENCE_SOURCE만** → 재평가 → Evidence Pack

---

## 9. Edition 반복 (Impact Analysis)

```
새 Source Evidence ↔ 기존 Claim
→ SUPPORTS | EXTENDS | CONTRADICTS | REPLACES
→ ImpactDecision: KEEP | UPDATE_CITATION | LIGHT_EDIT
                  | PARTIAL_REWRITE | FULL_REWRITE
                  | ADD_SECTION | REMOVE_SECTION
```

영향받은 장만 재실행.

---

## 10. 시각자료 · Export

**유형**: TABLE, COMPARISON_TABLE, BAR/LINE_CHART, PROCESS_FLOW, ARCHITECTURE_DIAGRAM, TIMELINE, MATRIX, SOURCE_FIGURE  

정량 근거 없으면 차트 대신 비교표·흐름도·구조도. 정성만이면 “자료 기반 정성 분석” 표기.

**Export 번들** (`edition-vN/`):

`report.md/.docx/.pdf`, `claim-evidence-ledger.xlsx`, `source-index.json`, `outline.json`, `review-summary.json`, `edition-diff.json`, `visuals/`

---

## 11. 데이터 · API · UI

### DB (MVP: SQLite)

`projects`, `sources`, `source_pages`, `content_blocks`, `visual_assets`, `metric_facts`,  
`corpus_snapshots`, `corpus_snapshot_sources`,  
`report_plans`, `outlines`, `outline_nodes`,  
`report_editions`, `sections`, `section_versions`,  
`evidence_items`, `claims`, `claim_evidence_links`,  
`reviews`, `review_issues`,  
`production_runs`, `production_tasks`, `artifacts`, `exports`

### API 그룹

Projects / Sources / Analyze / Plans·Outlines / Editions / Sections / Exports

### UI 7화면

프로젝트 · 자료 · 자료 분석 · 목차 편집 · 작성·검토 · Edition 비교 · 출력

---

## 12. 하드코딩 방지

1. 주제별 고정 목차 `if` 금지  
2. Agent instruction → `prompts/technical_analysis/*.md`  
3. 모델·retrieval·review 수치 → `config/*.yaml`  
4. Agent 출력 → JSON → Pydantic 검증 (실패 시 재요청 → 작업 실패)

---

## 13. 개발 Phase

| Phase | 범위 | 완료 기준 |
|-------|------|-----------|
| 1 | Project·Ingestion·Chunk·FTS5·Vector | 첨부 PDF 페이지별 텍스트/다이어그램/수치 조회 |
| 2 | Analyst·Planner·목차 UI·승인 | 다른 자료 → 다른 제목·목차 (코드 변경 없음) |
| 3 | Hybrid·Evidence·Writer·Claim 링크 | 문장 클릭 → 원본 페이지 |
| 4 | 병렬 Review·Gate·Reviser | 무근거·수치 오류 탐지·수정 |
| 5 | Visual·MD/DOCX/PDF | 흐름도·구성도·성과 차트 |
| 6 | Snapshot·Impact·Diff | 영향 장만 갱신 |

### MVP 파일 형식

1차: PDF, DOCX, MD, TXT (PPT 변환 PDF 포함)  
2차: PPTX, XLSX/CSV *(구현됨)* · HWP/HWPX *(미구현)*

---

## 14. 성공 조건 (다섯 기둥)

1. 원본을 정확히 읽는 기능  
2. 근거를 구조화하는 기능  
3. 자료에 맞는 분석 논리를 만드는 기능  
4. 작성 결과를 원문과 대조하는 기능  
5. 이전 버전의 좋은 부분만 안전하게 계승하는 기능  

이 다섯이 갖춰지면 주제 하드코딩 없이 전문가 기술분석서를 생성할 수 있다.
