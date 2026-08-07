# Technical Analysis Agent System
## AGENTS.md

# 1. Project Mission

이 프로젝트의 목적은 사용자가 제공한 PDF, 문서, URL 및 참고자료를 기반으로
전문적인 기술분석서를 생성하는 ADK 기반 멀티에이전트 시스템을 구축하는 것이다.

시스템의 핵심 목표는 “많은 Agent를 사용하는 것”이 아니다.

핵심 목표는:

- 자료 근거성
- 기술적 정확성
- 분석 깊이
- 보고서 전체 논리
- Chapter 간 일관성
- 재현 가능성
- 검토·수정 가능성
- 출처 추적 가능성
- 전문적인 최종 문서 품질

이다.

기능 수보다 결과물의 신뢰성과 품질을 우선한다.

# 2. Architecture Principle

시스템은 다음 세 계층을 명확하게 구분한다.

## A. Deterministic Layer

일반 Python 코드가 담당한다.

- 파일 저장
- PDF Parsing
- OCR
- ContentBlock 생성
- Chunking
- ID 생성
- Hash
- Embedding
- Retrieval
- Evidence Candidate 검색
- Evidence Validation
- Citation Mapping
- 분량 계산
- Schema Validation
- Artifact 저장
- Version 관리
- Workflow 상태 저장
- Retry
- Resume
- Export
- Diagram Rendering
- Chart Rendering
- DOCX/PDF 생성
- 깨진 문자 검사
- Placeholder 검사
- 내부 ID 노출 검사

결정론적으로 처리 가능한 작업에 LLM을 사용하지 않는다.

## B. Agent Intelligence Layer

ADK Agent가 담당한다.

- 자료 의미 분석
- 기술 주제 해석
- 보고서 전략 수립
- 목차 설계
- Chapter 작성
- 기술 검토
- 편집 검토
- 수정 방향 판단
- 전체 보고서 검토

시각자료 필요성 판단(Visual Planner)은
현재 기본 Agent 범위가 아니다.
필요성이 E2E에서 입증될 때만 검토한다.

## C. Workflow Layer

Agent 실행 순서와 상태를 관리한다.

Workflow가 Agent 실행 순서를 결정한다.

LLM Agent가 자유롭게 다음 Agent를 선택하지 않는다.

## D. Change and Duplication Policy

기존 프로젝트를 우선 활용한다.

새 구현을 추가하기 전에 반드시 동일하거나 유사한 책임의
기존 구현이 있는지 먼저 확인한다.

기존 구현에 대해 다음을 우선 판단한다.

- KEEP
- REFACTOR
- MOVE
- MERGE
- REPLACE
- REMOVE

기존 Canonical Owner를 확장하거나 정리해서 해결할 수 있다면
동일 책임의 새 구현을 병렬로 추가하지 않는다.

다음과 같은 구조는 특별한 이유 없이 만들지 않는다.

- agents_v2/
- workflows_new/
- services_v2/
- repository_new/
- prompts_v2/
- writer_new.py
- reviewer_v2.py

새 파일 또는 새 모듈이 실제로 필요한 경우에는 허용한다.

단 다음 조건을 만족해야 한다.

1. 기존 코드로 책임 있게 수용하기 어려운 이유가 명확할 것
2. 기존 Canonical Owner와 책임이 중복되지 않을 것
3. 새로운 Runtime Path를 병렬로 만들지 않을 것
4. 기존 구현을 대체하는 경우 제거 또는 통합 계획이 있을 것
5. 프로젝트의 기존 Directory 책임과 일치할 것

목표는 “새 파일을 만들지 않는 것”이 아니라
“같은 역할의 구현이 여러 군데 생기지 않도록 하는 것”이다.

Architecture Review는 대규모 구조 변경,
새 Runtime Layer 도입,
Canonical Owner 변경이 필요한 경우에만 수행한다.

일반적인 구현 세부사항이나 테스트 파일 추가까지
매번 별도 Architecture Review를 요구하지 않는다.

# 3. No DAG / No Parallel Chapter Writing / No Parallel Reviewers

이 프로젝트에서는 Chapter DAG Scheduler를 만들지 않는다.

Chapter Writer 병렬 실행도 하지 않는다.

Technical Reviewer와 Editorial Reviewer도
병렬(ThreadPool 등)로 실행하지 않는다.

Chapter 작성과 Review는 전부 순차적으로 수행한다.

예:

Chapter 1
→ Technical Review
→ Editorial Review
→ Revision (필요 시)
→ Finalize

Chapter 2
→ Technical Review
→ Editorial Review
→ Revision (필요 시)
→ Finalize

Chapter 3
→ ...

이유:

- Chapter 간 문맥 연결
- 용어 일관성
- 앞 Chapter 내용 참조
- 반복 방지
- 전체 보고서 흐름 유지
- 복잡한 Scheduler 제거
- Review 결과 재현성·디버깅 가능성

가속보다 문서 품질과 구조적 단순성을 우선한다.

ParallelAgent 또는 자체 Chapter 병렬 Scheduler를
추가하지 않는다.

기존 ReviewLoop의 Reviewer 병렬 실행은
Review/Revision 정리 Phase에서 순차 실행으로 교체한다.

# 4. Canonical Workflow

전체 표준 실행 흐름은 다음과 같다.

SOURCE INGESTION

→ EVIDENCE CONSTRUCTION

→ SOURCE INTELLIGENCE

→ REPORT STRATEGY

→ OUTLINE

→ OUTLINE REVIEW

→ USER PLAN APPROVAL

→ CHAPTER WRITING LOOP

→ VISUAL RENDERING
  (현재: deterministic VisualService.
   Visual Planner Agent는 기본 범위가 아니며,
   E2E에서 필요성이 입증될 때만 검토한다.)

→ FULL REPORT REVIEW

→ FINAL REVISION

→ PUBLICATION

각 Stage는 명확한 Input/Output Artifact를 가진다.

# 5. Planning Workflow

Planning은 다음 순서를 따른다.

Source Intelligence Agent

→ Report Strategist Agent

→ Outline Architect Agent

→ Outline Reviewer Agent

→ Deterministic Planning Gate

→ User Approval

사용자가 계획을 승인하기 전에는
Chapter Writer를 실행하지 않는다.

Approved Plan은 Production 단계의 기준이 된다.

Production 단계 Agent가 임의로 전체 목차를 변경하지 않는다.

# 6. Chapter Writing Loop

각 Chapter는 다음 흐름으로 순차 처리한다.

Chapter Context Builder
(Python)

→ Chapter Writer Agent

→ Draft Validator
(Python)

→ Technical Reviewer Agent

→ Editorial Reviewer Agent

→ Review Issue Aggregator
(Python)

→ Quality Gate
(Python)

PASS
→ Final Chapter

REVISION_REQUIRED
→ Reviser Agent
→ Validator
→ 필요한 Reviewer 재검토
→ Quality Gate

한 Chapter가 확정된 뒤 다음 Chapter로 이동한다.

# 7. Revision Policy

전체 Chapter를 무조건 다시 작성하지 않는다.

Reviewer는 구조화된 Review Issue를 생성한다.

Reviser는 Issue가 지적한 범위만 수정한다.

예:

- 근거 부족
- 기술 설명 오류
- 논리 비약
- 반복
- 문체 문제
- 분량 부족
- Citation 오류

Revision 횟수는 제한한다.

기본 정책:

MAX_REVISION = 2

실제 값은 Config에서 관리한다.

무한 Review Loop를 만들지 않는다.

# 8. Agent Roles

## Source Intelligence Agent

자료 전체의 성격과 기술적 의미를 분석한다.

Output:
SOURCE_PROFILE

포함:

- 자료 요약
- 주요 기술 주제
- 핵심 개념
- 강점
- 한계
- 분석 가능 영역
- 주요 Theme

────────────────

## Report Strategist Agent

보고서 작성 전략을 만든다.

Output:
REPORT_STRATEGY

포함:

- 보고서 목적
- 예상 독자
- 작성 언어
- 분석 관점
- 핵심 질문
- 포함 범위
- 제외 범위
- 기술적 깊이
- 전체 목표 분량
- 보고서 작성 원칙

────────────────

## Outline Architect Agent

보고서 목차를 설계한다.

Output:
OUTLINE_PLAN

각 Chapter에 최소:

- title
- objective
- core_message
- analysis_questions
- evidence_themes
- importance
- target_length
- visual_candidates

를 고려한다.

Chapter Dependency/DAG는 만들지 않는다.

────────────────

## Outline Reviewer Agent

목차의 품질을 검토한다.

검토:

- 보고서 목적과 정합성
- 기술적 흐름
- 누락
- 중복
- Chapter 순서
- 분석 깊이
- Evidence Coverage
- 분량 균형

Output:
OUTLINE_REVIEW

────────────────

## Chapter Writer Agent

한 번에 하나의 Chapter만 작성한다.

Input:

- APPROVED_PLAN
- CURRENT_CHAPTER_PLAN
- EVIDENCE_PACK
- PREVIOUS_FINAL_CHAPTER_SUMMARY
- REPORT_STYLE
- LANGUAGE
- TARGET_LENGTH

Writer는 다음을 하지 않는다.

- 자료 검색
- Evidence 생성
- 전체 목차 변경
- Review 판정
- Citation 번호 생성
- 최종 Export

Output:
CHAPTER_DRAFT

────────────────

## Technical Reviewer Agent

검토:

- 기술적 정확성
- Evidence Grounding
- 근거 없는 주장
- 수치 정확성
- 논리 비약
- Citation 근거
- 기술 용어 정확성

Output:
TECHNICAL_REVIEW

────────────────

## Editorial Reviewer Agent

검토:

- 전문성
- 구조
- 반복
- 가독성
- 문체
- 용어 일관성
- 앞 Chapter와 연결
- 문장 품질

Output:
EDITORIAL_REVIEW

────────────────

## Reviser Agent

Structured Review Issue를 입력받아
필요한 부분만 수정한다.

Output:
REVISED_CHAPTER

Writer 역할을 다시 수행하지 않는다.

────────────────

## Visual Planner Agent (LATER — 기본 범위 아님)

현재 Runtime은 deterministic VisualService가
VisualRequest 렌더링을 담당한다.

Visual Planner Agent는 지금 추가하지 않는다.

“MISSING”이라는 이유만으로 Agent를 추가하지 않는다.

실제 E2E 결과에서
“어떤 시각자료가 필요한지 판단하는 기능이 부족하다”
가 확인됐을 때만 추가 여부를 검토한다.

추가 시 책임:

- 표 / 비교표 / Architecture / Process / Flow / Chart / Timeline / Concept 필요성 판단
- Output: VISUAL_PLAN

최종 PNG/SVG 렌더링은 Agent가 아닌
Rendering Service가 담당한다.

# 9. Full Report Review

Chapter 작성이 모두 완료된 뒤 전체 보고서를 검토한다.

새로운 Reviewer Agent를 무조건 만들지 않는다.

가능하면 기존 Reviewer를 재사용한다.

Technical Reviewer:
mode = FULL_REPORT

Editorial Reviewer:
mode = FULL_REPORT

전체 검토 항목:

- Chapter 간 모순
- 중복
- 용어 통일
- 기술적 연결
- 보고서 목적 달성
- Evidence 분포
- 서론/본론/결론 흐름
- 전체 분량 균형

필요하면 Final Reviser가 수정한다.

# 10. Evidence Architecture

Evidence는 LLM Agent가 임의로 생성하지 않는다.

표준 흐름:

Source

→ ContentBlock

→ Retrieval

→ Candidate

→ Deterministic Validation

→ Evidence

→ Evidence Pack

Evidence는 원문 위치와 추적 가능해야 한다.

최소 개념:

- evidence_id
- source_id
- block_id
- source_location
- normalized_statement
- supporting_text
- theme
- evidence_type
- confidence
- provenance

Evidence Schema를 수정할 때는
현재 프로젝트 구조를 우선 분석한다.

불필요한 신규 Schema를 만들지 않는다.

# 11. Artifact First

Agent 간 결과 전달은 가능한 한
Typed Artifact를 사용한다.

긴 문자열 Prompt를 Agent끼리 직접 전달하지 않는다.

대표 Artifact:

SOURCE_PROFILE
EVIDENCE_PACK
REPORT_STRATEGY
OUTLINE_PLAN
OUTLINE_REVIEW
APPROVED_PLAN
CHAPTER_PLAN
CHAPTER_DRAFT
TECHNICAL_REVIEW
EDITORIAL_REVIEW
REVISED_CHAPTER
VISUAL_PLAN
FINAL_CHAPTER
FULL_REPORT_REVIEW
FINAL_REPORT

Artifact는 Version을 가진다.

현재 Runtime의 `artifacts` table이 이미 존재한다.

새 `artifact_v2` 또는 별도 Artifact DB 구조를 만들지 않는다.

먼저 기존 `artifacts` table로
version / provenance / Agent output 저장이 가능한지 확인한다.

충분하면 기존 table을 Canonical로 사용한다.

부족한 경우에만 최소 additive migration을 검토한다.

평행 Artifact Schema를 만들지 않는다.

기존 저장 구조로 표현 가능한 경우
새 Artifact 테이블을 무조건 만들지 않는다.

# 12. Workflow State != Artifact

Workflow State와 Artifact를 구분한다.

State:

- queued
- running
- waiting_for_approval
- reviewing
- revising
- completed
- failed
- cancelled

Artifact:

실제 생성 결과.

Workflow가 실패해도 완료된 Artifact를 삭제하지 않는다.

# 13. Failure / Resume

장시간 Workflow는 Resume 가능해야 한다.

예:

Planning 완료
Chapter 1 완료
Chapter 2 작성 완료
Chapter 2 Review 실패

재실행:

Chapter 2 Review부터 Resume

처음 Source 단계부터 다시 실행하지 않는다.

완료 Artifact를 재사용한다.

Retry와 Resume를 구분한다.

# 14. Quality Gate

LLM 출력이 존재한다고 성공으로 판정하지 않는다.

각 Stage에 Gate가 있다.

Planning Gate:

- 필수 필드
- 빈 제목
- 목차 구조
- Evidence Coverage
- 사용자 승인

Chapter Draft Gate:

- 빈 본문
- 분량
- 이상 문자
- Placeholder
- 내부 ID
- Citation 형식

Review Gate:

- Critical Issue
- Major Issue
- Revision Limit

Publication Gate:

- 모든 Chapter 완료
- Citation resolved
- Visual resolved
- Placeholder 없음
- 내부 ID 없음
- 깨진 문자 없음

가능한 항목은 Python으로 검사한다.

# 15. Structured Review Issue

Reviewer 결과는 자유 텍스트 한 덩어리만 반환하지 않는다.

Review Issue에는 최소:

- issue_id
- chapter_id
- severity
- category
- location
- problem
- required_change
- evidence_refs

를 고려한다.

Reviser는 이 Issue를 직접 사용한다.

# 16. Language Policy

report_language는 Planning부터 Publication까지 상속한다.

예:

report_language = ko

적용 대상:

- 제목
- Report Strategy
- Outline
- Chapter Writer
- Technical Review
- Editorial Review
- Revision
- 표
- 그림 Caption
- Final Report

Frontend에서 번역해서 해결하지 않는다.

Agent 생성 시점부터 지정 언어를 사용한다.

# 17. Length Policy

전체 목표 분량은 Report Strategy에 저장한다.

Chapter 목표 분량은 Outline/Chapter Plan에 저장한다.

사용자는 가능한 한:

- 전체 목표 분량
- Chapter 중요도

를 설정한다.

시스템이 Chapter 권장 분량을 계산한다.

Writer는 target_length를 입력받는다.

Draft Validator가 실제 분량을 계산한다.

허용 범위를 벗어나면 Review Issue로 연결한다.

# 18. Citation Policy

LLM이 최종 Citation 번호를 임의 생성하지 않는다.

Writer는 Evidence Reference를 구조적으로 기록한다.

Deterministic Citation Service가:

Evidence Reference
→ Source
→ 원문 위치
→ 최종 Citation

으로 변환한다.

UUID, block_id, evidence_id 같은 내부 ID를
최종 사용자 문서에 노출하지 않는다.

# 19. Visual Policy

현재 Canonical:

deterministic VisualService / Renderer가
VisualRequest를 실제 결과로 만든다.

기본:

- SVG
- Mermaid/Graphviz 등 deterministic renderer
- Chart library
- Table renderer

생성형 이미지는 별도 선택 기능으로 둔다.

Visual Planner Agent가 도입되는 경우에만
“무엇을 시각화할지” 판단을 Agent가 담당한다.

예:

{
  visual_type,
  purpose,
  entities,
  relations,
  data,
  caption,
  source_refs
}

도입 전까지는 Writer/Plan의 VisualRequest와
deterministic 렌더링 경로를 유지한다.

# 20. Prompt Policy

Prompt를 Agent Python 코드에 장문의 문자열로 계속 추가하지 않는다.

Prompt Asset을 역할별로 관리한다.

예:

prompts/
  common/
  source/
  planning/
  writing/
  review/
  revision/
  visual/

Prompt에는 version을 관리할 수 있어야 한다.

Prompt 수정 시 Parser/Schema/Test와 함께 검토한다.

# 21. Model Policy

Model 이름을 Agent 코드에 직접 하드코딩하지 않는다.

Config / Model Registry를 사용한다.

역할별 모델 변경이 가능해야 한다.

예:

creator
critic

하지만 모델이 늘어났다고 Agent를 복제하지 않는다.

# 22. ADK Usage Policy

ADK를 형식적으로만 사용하지 않는다.

이름만 붙은 Wrapper로 ADK를 쓰지 않는다.

최종 방향:

Agent
→ ADK Agent execution
→ thin model adapter
→ canonical model_providers

Model Access의 Canonical Owner는
`backend/model_providers`이다.

ADK 때문에 동일 Ollama/httpx 호출을 다시 구현한
두 번째 Gateway를 만들지 않는다.

`backend/adk_app`은 영구적인 두 번째 Agent Tree가 아니다.

Migration Adapter 역할만 허용한다.

기존 `backend/agents`가 실제 ADK 실행을 소유하게 되면
불필요해진 `adk_app` scaffold는 제거한다.

ADK Agent 객체만 정의하고
기존 LLM 직접 호출을 그대로 두는 이중 실행 경로를 만들지 않는다.

다음 책임을 구분한다.

ADK:
- Agent 역할
- Agent execution
- Agent context

Python / Orchestration:
- Workflow orchestration
- Storage
- Retrieval
- Validation
- Artifact
- State
- Rendering
- Export

# 23. No Unnecessary A2A / MCP

현재 시스템은 하나의 Backend 내부 멀티에이전트 시스템이다.

필요하지 않은:

- A2A
- MCP
- distributed scheduler
- agent mesh
- message broker

를 아키텍처 장식용으로 추가하지 않는다.

외부 시스템 연결이 실제로 필요해질 때만 검토한다.

# 24. Sequential First

구조의 기본 원칙은 단순한 순차 실행이다.

성능 최적화를 이유로:

- Chapter 병렬화
- Reviewer 병렬화
- DAG
- 복잡한 Scheduler
- 분산 Queue

를 선제적으로 도입하지 않는다.

현재 시스템에서 실제 병목이 측정된 후에만
별도 개선 과제로 검토한다.

# 25. User Approval

최소 Human-in-the-loop 지점:

Planning Approval

사용자가 확인:

- 작성 언어
- 제목
- 목적
- 예상 독자
- 전체 분량
- 목차

승인 후 Writing 시작.

불필요하게 승인 단계를 여러 개 만들지 않는다.

# 26. UI Independence

현재 다른 프로젝트의 Frontend UI를 복사하지 않는다.

특히 다음을 아키텍처 규칙으로 간주하지 않는다.

- Stepper
- Navigation
- Proposal UI
- Planning Workspace UI
- Sidebar 구조
- 버튼 구조
- Version UI

Backend Architecture와 UI Architecture를 분리한다.

UI는 현재 기술분석서 프로젝트의 사용 목적에 맞춰 별도로 설계한다.

# 27. Existing Code First

항상 기존 코드를 먼저 확인한다.

새 파일을 만드는 것보다:

KEEP
REFACTOR
MOVE
MERGE
REPLACE
REMOVE
MISSING

를 먼저 판단한다.

세부 정의와 적용 절차는
§34 Adapt Architecture to Existing Project 및
§33–58 Existing Project Adaptation / Cleanup / Structure Policy를 따른다.

기존 코드가 있는데 비슷한 새 시스템을 옆에 추가하지 않는다.

새 구현과 Legacy 구현을 동시에 유지하는 Dual Path를 피한다.

일시 Migration Adapter가 필요하면 §36에 따라
필요성·대체 대상·제거 조건·제거 Phase를 명시한 뒤,
검증 완료 시 Legacy 경로를 삭제한다.

# 28. No Silent Fallback

LLM/Parser/Validator/ADK 실행 실패를
임의 기본값으로 성공 처리하지 않는다.

금지:

- 실패 → 빈 문자열 → 성공
- Schema 오류 → raw response 저장 → 성공
- Evidence 없음 → 가짜 Evidence
- Review 오류 → PASS
- Model 오류 → Mock 결과
- ADK FAILED → offline fallback → COMPLETED

Offline mode가 필요하면:

config/사용자가 명시적으로 선택
→ offline execution
→ provenance=offline

처럼 별도 실행 모드로 관리한다.

Silent fallback으로 online 실패를
성공처럼 보이게 하지 않는다.

Fallback이 존재하면 명시적으로 상태와 provenance를 기록한다.

# 29. Testing Policy

각 단계는 최소 다음을 테스트한다.

- Schema
- Parser
- Service
- Agent Contract
- Artifact Persistence
- Workflow State
- Resume
- Failure
- Gate

Live LLM Test와 일반 Unit Test를 분리한다.

실제 사용자 데이터에 자동 write E2E를 반복 실행하지 않는다.

테스트 전용 Project/Fixture를 사용한다.

# 30. Completion Policy

다음 상태에서는 완료라고 말하지 않는다.

- TODO 존재
- Mock 사용
- 항상 PASS Validator
- Artifact 저장 없음
- 실패 상태 저장 없음
- 실제 Agent 연결 없음
- 테스트 없음
- Schema와 Prompt 불일치
- 사용하지 않는 Legacy Path 존재
- Secret 하드코딩
- 내부 ID가 최종 결과에 노출

# 31. Development Procedure

모든 이후 작업은 반드시:

1. AGENTS.md 읽기
2. 현재 구현 분석
3. 범위 확정
4. 최소 수정 설계
5. 구현
6. 관련 테스트
7. 전체 회귀 확인
8. 상태/Artifact 검증
9. 완료 보고

순서로 수행한다.

AGENTS.md와 충돌하는 요구가 나오면
임의로 구현하지 말고 충돌 내용을 먼저 보고한다.

# 32. Core Principle

이 프로젝트의 우선순위는:

1. 정확한 근거
2. 기술적 분석 품질
3. 일관된 문서 구조
4. 검토 가능한 결과
5. 재현 가능한 Workflow
6. 실패 복구
7. 단순한 Architecture
8. 성능 최적화

이다.

복잡한 멀티에이전트 Architecture 자체가 목표가 아니다.

전문적인 기술분석서를 안정적으로 생산하는 것이 목표다.

# Existing Project Adaptation / Cleanup / Structure Policy

이 프로젝트는 새로운 ADK 코드를 기존 코드 옆에 계속 추가하는 방식으로
개편하지 않는다.

현재 프로젝트의 실제 코드와 Runtime을 기준으로
기존 기능을 유지하면서 점진적으로 구조를 교체하고,
교체가 끝난 Legacy 코드는 제거하는 방식으로 진행한다.

# 33. Current Runtime Is the Source of Truth

설계 문서나 파일 이름보다
현재 실제 Runtime에서 호출되는 코드가 우선이다.

리팩터링 전에는 반드시:

Frontend Action
→ API
→ Application/Workflow
→ Agent/Service
→ Persistence
→ Response

실제 호출 경로를 확인한다.

파일이 존재한다는 이유로
현재 사용 중이라고 판단하지 않는다.

반대로 이름이 Legacy처럼 보여도
실제 Runtime에서 사용되고 있다면
분석 없이 삭제하지 않는다.

모든 구조 변경은 현재 Runtime을 기준으로 한다.

# 34. Adapt Architecture to Existing Project

AGENTS.md의 목표 Architecture를
현재 프로젝트에 기계적으로 덮어씌우지 않는다.

항상 먼저 현재 구현을 분석하고
각 기능을 다음으로 분류한다.

KEEP
현재 구현이 책임과 구조에 적합하므로 유지.

REFACTOR
기능과 책임은 유지하되 구조 또는 위치를 개선.

MOVE
코드는 유효하지만 디렉터리 위치가 잘못되어 이동.

MERGE
동일 책임의 여러 구현을 하나로 통합.

REPLACE
현재 구현을 새 Canonical 구현으로 교체.

REMOVE
더 이상 필요하지 않거나 교체 완료된 코드.

MISSING
현재 없으며 실제로 필요한 핵심 기능.

목표 Architecture에 같은 역할이 있다고 해서
새 파일을 바로 생성하지 않는다.

현재 구현 중 재사용 가능한 것이 있는지 먼저 찾는다.

# 35. One Responsibility, One Canonical Owner

하나의 책임은 최종적으로 하나의 Canonical 구현만 가져야 한다.

예:

Chapter Writing
→ ChapterWriterAgent

Technical Review
→ TechnicalReviewerAgent

Editorial Review
→ EditorialReviewerAgent

Revision
→ ReviserAgent

Evidence Validation
→ EvidenceValidator

Citation Resolution
→ CitationService

Model Access
→ Model Gateway / Registry

Artifact Persistence
→ Artifact Repository

동일한 책임을 수행하는 구현이
서로 다른 디렉터리에 여러 개 존재하도록 두지 않는다.

다음과 같은 상태를 금지한다.

writer.py
writer_service.py
writer_skill.py
writer_agent.py
chapter_generator.py

가 모두 Chapter 작성 LLM을 직접 호출하는 상태.

이 경우 최종 Canonical Owner 하나를 결정하고
나머지는:

MERGE
REPLACE
REMOVE

중 하나로 처리한다.

# 36. No Dual Runtime

신규 ADK Runtime과 기존 Legacy Runtime을
장기간 동시에 유지하지 않는다.

금지:

OldWriter
+
NewADKWriter

두 경로가 모두 API에서 호출 가능한 상태.

일시적인 Migration Adapter가 필요할 수는 있다.

하지만 Adapter에는 반드시:

- 왜 필요한지
- 어떤 Legacy 경로를 대체하는지
- 제거 조건
- 제거 Phase

가 명시되어야 한다.

새 경로가 검증되면
이전 실행 경로를 제거한다.

# 37. Replacement Means Deletion

기존 코드를 새 구현으로 교체했다고 해서
이전 코드를 그대로 남겨두지 않는다.

교체 완료 조건:

1. 모든 Runtime 호출이 신규 구현을 사용
2. 관련 테스트가 신규 구현 기준으로 통과
3. Import reference가 없음
4. API가 Legacy 경로를 사용하지 않음
5. DB/Artifact compatibility 확인
6. rollback 기준점 확보

이 조건이 만족되면
Legacy 구현을 삭제한다.

“혹시 나중에 쓸 수도 있으니까”
라는 이유로 Dead Code를 저장소에 유지하지 않는다.

Git이 이전 코드를 보존한다.

# 38. Duplicate Implementation Audit

모든 Phase 시작 전에
해당 책임의 중복 구현을 검색한다.

검색 대상:

- 동일/유사 class 이름
- 동일 Prompt
- 동일 LLM 호출
- 동일 API 목적
- 동일 Repository query
- 동일 Schema
- 동일 Validator
- 동일 parsing
- 동일 Gateway
- 동일 State transition
- 동일 Artifact 생성
- 동일 Retry/Timeout 로직

파일 이름이 달라도
실제 책임이 같으면 중복으로 본다.

중복 판정은 이름이 아니라 행동 기준이다.

# 39. Canonical Responsibility Registry

Architecture 개편 중
각 핵심 책임의 Canonical Owner를 명확히 관리한다.

최종 Registry(Repository Audit + Schema Audit 기준):

| Responsibility | Canonical Owner | Legacy / 조치 |
|----------------|-----------------|---------------|
| HTTP Boundary | `backend/api/*` | KEEP; thin 유지 |
| Use-case Facade | `backend/services/*` | KEEP; orchestration 직접 소유 축소는 점진 |
| Workflow Orchestration | `backend/orchestration/*` | KEEP; `report_orchestrator.py` → REMOVE (Phase 0) |
| Source Intelligence | `agents/corpus_analyst` | KEEP; ADK dual path MERGE (Phase 1/6) |
| Report Strategy | `agents/report_strategist` | KEEP |
| Outline Architect | `agents/report_planner` (통합 후 OutlineArchitect) | `outline_designer` wrapper → MERGE/REMOVE (Phase 2) |
| Outline Review | `agents/outline_critic` + deterministic Planning Gate | KEEP (역할 분리) |
| Chapter Writing | `agents/chapter_writer` | KEEP; contract 통일 (Phase 3) |
| Technical Review | `agents/technical_reviewer` | KEEP; 순차 실행 (Phase 4) |
| Editorial Review | `agents/editorial_reviewer` | KEEP; 순차 실행 (Phase 4) |
| Revision | `agents/reviser` | KEEP; targeted issue만 (Phase 4) |
| Evidence Pack | `EvidencePackService` + `skills/retrieval` | KEEP; `evidence_refine` → 추가 확인 후 |
| Citation Resolution | Citation 관련 skill/service (정리 Phase 7) | 분산 → 단일 Owner로 REFACTOR |
| Visual Rendering | deterministic VisualService | KEEP; Visual Planner Agent = LATER |
| Publication / Export | `finalization_pipeline` + exporters | KEEP |
| Model Access | `backend/model_providers` | KEEP Canonical; ADK는 thin adapter만 |
| Prompt Loading | `agents/prompt_loader` | `adk_app` loader → MERGE/REMOVE |
| Artifact Persistence | v1 `artifacts` (+ repos) | 새 artifact schema 금지; write 경로 보강 검토 |
| Chapter Persistence | v1 `sections` / `section_versions` | Domain=Chapter, DB=section; v2 chapters → RETIRE |
| Review Persistence | v1 `reviews.section_id` | v2 `reviews.chapter_id` → RETIRE |
| Workflow State | `ProjectStage` + `state_machine` | KEEP; job_status는 projection |
| ADK Migration Adapter | `backend/adk_app` (임시) | agents가 ADK 실행 소유 후 REMOVE |

이 정보를 Architecture Audit과
Migration Plan에서 지속적으로 갱신한다.

새로운 구현을 만들기 전에
동일 Responsibility의 Canonical Owner가
이미 존재하는지 확인한다.

예 형식(변경 시 동일 표로 갱신):

Responsibility:
Chapter Writing

Canonical:
backend/agents/chapter_writer

Called By:
backend/orchestration/production_pipeline.py

Input:
ChapterContext

Output:
ChapterDraft

Legacy:
agents/technical_writer/ → REMOVE
outline_designer wrapper → MERGE

# 40. Directory Has Meaning

파일 위치는 책임을 나타내야 한다.

비슷한 책임의 파일이
저장소 곳곳에 흩어져 있으면 안 된다.

현재 Runtime 기준 Canonical Directory:

```
backend/api/              # HTTP boundary
backend/services/         # thin use-case facade
backend/orchestration/    # canonical workflow
backend/agents/           # LLM/ADK reasoning roles
backend/skills/           # deterministic processing
backend/domain/           # canonical domain contracts
backend/storage/          # persistence (v1 migrations Canonical)
backend/model_providers/  # model access
backend/adk_app/          # TEMP Migration Adapter only → shrink/delete
prompts/                  # prompt source of truth
config/                   # runtime/model config
frontend/
tests/
```

신규 top-level 평행 구조 금지:

- `agents_v2/`
- `agents_new/`
- `workflows_new/`
- `new_runtime/`
- `writer_v2/`
- `reviewer_v2/`
- `services_v2/`
- `domain_v2/`

파일 이동은 COPY가 아니라 MOVE/MERGE를 원칙으로 한다.

예시 구조를 무조건 새로 만들지 않는다.
현재 Repository Tree를 가능한 한 활용한다.

# 41. No Mixed Responsibility Directory

다음과 같은 구조를 만들지 않는다.

utils/
  writer.py
  evidence.py
  prompt.py
  database.py
  reviewer.py

common/
  agent.py
  export.py
  planning.py

misc/
helpers/

처럼 책임이 불명확한 디렉터리에
핵심 Domain 코드를 계속 넣지 않는다.

utils/common/helpers는
정말 Domain-independent한 작은 기능에만 사용한다.

핵심 비즈니스 책임은
명확한 Domain 또는 Layer에 위치해야 한다.

# 42. Dependency Direction

의존 방향을 명확히 한다.

기본 원칙:

API
↓
Workflow / Application
↓
Agent + Deterministic Service
↓
Domain Contract
↓
Repository / Gateway

API Route가 직접:

- Model Gateway
- DB Session query
- Prompt
- LLM Agent

를 조합하지 않는다.

Agent가 API Router를 import하지 않는다.

Domain이 Frontend/API에 의존하지 않는다.

Persistence가 Agent를 호출하지 않는다.

순환 import를 만들지 않는다.

# 43. API Must Stay Thin

API Layer 책임:

- Request validation
- Authorization
- Application 호출
- Response mapping
- HTTP status

API Route 안에서:

- Prompt 작성
- Agent orchestration
- Evidence 생성
- Review 판단
- DB business logic
- Export orchestration

을 직접 구현하지 않는다.

# 44. Agent Must Stay Focused

Agent 하나에 여러 비즈니스 역할을 누적하지 않는다.

예:

Writer가:

- Retrieval
- Planning
- Writing
- Review
- Revision
- Export

을 모두 하지 않는다.

Agent는 하나의 판단 책임을 가진다.

그러나 동일 역할을 지나치게 세분화해
Agent 수를 늘리는 것도 피한다.

“책임 분리”와 “Agent 남발”을 구분한다.

# 45. Service Must Not Become Agent Shadow

Agent를 도입한 뒤
기존 Service가 같은 LLM 역할을 그대로 수행하는 구조를 금지한다.

예:

ChapterWriterAgent
→ 실제로는 ChapterWriterService.generate()
→ 내부에서 LLM 직접 호출

이 구조에서 Agent가 단순 Wrapper라면 잘못된 것이다.

LLM reasoning 책임은 Agent가 가져간다.

Service는:

- Context Build
- Retrieval
- Validation
- Persistence
- deterministic transform

등을 담당한다.

# 46. Schema Ownership

같은 개념의 Schema를 여러 곳에서 정의하지 않는다.

예:

ChapterDraft
ChapterDraftResponse
WriterOutput
GeneratedChapter
ChapterContent

가 사실상 같은 데이터를 표현한다면
Canonical Domain Schema를 정의하고
API Schema는 필요한 Boundary Mapping만 수행한다.

Schema 중복은
Prompt/Parser/DB mismatch의 주요 원인이므로
Phase마다 검사한다.

# 47. Prompt Ownership

같은 역할의 Prompt가 여러 곳에 존재하지 않는다.

예:

agents/writer.py `_SYSTEM`
services/writer_prompt.py
prompts/chapter_writer.md

가 동시에 사용되지 않도록 한다.

최종 Prompt Source of Truth를 하나로 만든다.

Legacy Prompt를 더 이상 사용하지 않으면 삭제한다.

# 48. Gateway Ownership

동일 Provider/Model을 호출하는 Gateway가
중복 존재하지 않도록 한다.

직접 httpx 호출
+
Ollama Client
+
ModelGateway
+
ADK custom model adapter

가 동일 목적을 수행한다면
실제 필요성을 분석하고
최종 Model Access 경로를 하나로 정리한다.

ADK가 요구하는 Adapter와
Domain Gateway가 필요하다면
책임을 명확히 구분한다.

동일 호출을 구현한 두 Gateway는 허용하지 않는다.

# 49. State Ownership

Project Status,
Workflow Status,
Job Status,
Artifact Status,
Chapter Status

를 무분별하게 중복 정의하지 않는다.

각 State가 무엇을 표현하는지 명확히 한다.

같은 상태 의미를:

processing
running
generating
in_progress

처럼 여러 Enum으로 중복 관리하지 않는다.

필요하다면 Canonical State와
UI 표시 상태를 분리한다.

# 50. File Move Is a Refactor, Not a Copy

디렉터리 재구성 시:

기존 파일 COPY
→ 새 파일 생성
→ 기존 파일 방치

방식을 사용하지 않는다.

MOVE 또는
내용 통합 후 기존 파일 DELETE 방식으로 진행한다.

이동 후:

- import
- test
- config
- documentation
- runtime entrypoint

를 모두 갱신한다.

# 51. No Orphan Code

다음 코드를 남기지 않는다.

- Import되지 않는 핵심 Module
- 사용되지 않는 Agent
- 사용되지 않는 Prompt
- API가 없는 Service
- 호출되지 않는 Repository
- Migration 완료 후 남은 Legacy Adapter
- 테스트만 참조하는 구 구현
- NotImplemented placeholder
- deprecated duplicate

의도적으로 보존해야 하면
이유와 제거 조건을 문서화한다.

# 52. Migration by Vertical Slice

전체 프로젝트를 한 번에 새 구조로 복사하지 않는다.

책임 단위 Vertical Slice로 전환한다.

예:

Planning 개편:

현재 Planning Runtime 분석
→ Canonical Planning 책임 결정
→ 기존 코드 재사용/통합
→ ADK Planning 연결
→ 테스트
→ 실제 Runtime 전환
→ Legacy Planning 삭제
→ 다음 Phase

Writing도 동일하게 진행한다.

새 구조 전체를 먼저 만들고
나중에 연결하는 방식은 피한다.

# 53. Cleanup Is Part of Each Phase

Cleanup을 프로젝트 마지막으로만 미루지 않는다.

각 Phase 완료 조건에 반드시 포함한다.

- 대체된 코드 삭제
- 사용하지 않는 imports 삭제
- Legacy Prompt 삭제
- Legacy test 수정/삭제
- 중복 Schema 통합
- Dead API 제거
- Directory 정리

다만 아직 다음 Phase에서 사용되는
공통 Legacy 코드까지 성급하게 삭제하지 않는다.

# 54. Delete Safely

삭제 전 반드시 확인:

1. ripgrep/reference search
2. import graph
3. API route usage
4. test usage
5. runtime startup
6. DB/Migration dependence
7. config reference
8. frontend dependency
9. CLI/script dependency
10. documentation/runtime command

삭제는 추정으로 하지 않는다.

# 55. No Premature Target Directory

Architecture Audit 전에
목표 디렉터리를 무조건 생성하지 않는다.

먼저 현재 Repository 구조와 Runtime을 분석한다.

그 후:

현재 구조를 유지하는 비용
vs
파일 이동 비용

을 비교한다.

파일 이동이 명확한 이점이 있을 때만 이동한다.

“예쁜 Tree” 자체가 목표가 아니다.

책임 경계가 명확한 Tree가 목표다.

# 56. Structural Completion Criteria

Architecture Migration 완료 시 다음을 만족해야 한다.

- 하나의 책임에 하나의 Canonical 구현
- Dual Runtime 없음
- Legacy LLM path 없음
- 사용하지 않는 Agent 없음
- 중복 Prompt 없음
- 중복 Gateway 없음
- 중복 핵심 Schema 없음
- 사용하지 않는 핵심 Service 없음
- 순환 dependency 없음
- Runtime Entry Point 명확
- Directory별 책임 명확
- 모든 주요 코드가 Runtime 또는 명시적 Library로 사용됨
- 테스트가 Canonical Path를 검증
- 최종 문서에 내부 ID 노출 없음
- AGENTS.md Architecture와 실제 Runtime이 일치

# 57. Refactor Decision Rule

기존 코드가 목표 책임을 이미 잘 수행하면 KEEP한다.

70~80% 이상 재사용 가능하면 REFACTOR를 우선한다.

동일 책임 구현이 여러 개면 MERGE를 우선한다.

책임 자체가 잘못되었거나
새 구조와 양립 불가능하면 REPLACE한다.

Runtime에서 사용되지 않고
향후 필요성도 없으면 REMOVE한다.

새 파일 생성은 마지막 선택지다.

# 58. Repository Quality Principle

최종 Repository는
기능이 작동하는 것뿐 아니라
새 개발자가 Tree를 보고 다음을 이해할 수 있어야 한다.

- Agent는 어디에 있는가
- Workflow는 어디에 있는가
- Evidence는 어디에서 처리되는가
- Writing은 어디에서 처리되는가
- Review는 어디에서 처리되는가
- Prompt는 어디에 있는가
- DB 저장은 어디에서 처리되는가
- Model 호출은 어디에서 처리되는가
- Export는 어디에서 처리되는가

동일 책임을 찾기 위해
저장소 전체를 검색해야 하는 구조를 만들지 않는다.

# Final Architecture Decision
# (Repository Audit + Schema Audit 확정)

# 59. Existing Runtime Is Canonical

Greenfield 재작성하지 않는다.

현재 실제 Runtime의 핵심:

- `backend/orchestration`
- `backend/agents`
- `backend/model_providers`

를 Canonical 기반으로 유지한다.

새 코드를 기존 코드 옆에 계속 추가하는 방식을 금지한다.

현재 동작하는 코드를 분석하고
KEEP / REFACTOR / MOVE / MERGE / REPLACE / REMOVE
방식으로 정리한다.

# 60. Final Sequential Runtime

최종 실행 흐름:

```
SOURCE INGESTION
→ EVIDENCE CONSTRUCTION
→ SOURCE INTELLIGENCE (CorpusAnalyst)
→ REPORT STRATEGY (ReportStrategist)
→ OUTLINE ARCHITECT (단일 OutlineArchitect; OutlineDesigner/ReportPlanner 중복 제거)
→ OUTLINE REVIEWER
→ deterministic Planning Gate
→ USER PLAN APPROVAL
→ CHAPTER WRITING LOOP (순차):
     Context Builder
   → Chapter Writer
   → Draft Validator
   → Technical Reviewer
   → Editorial Reviewer
   → Issue Aggregator
   → Quality Gate
   → (필요 시) Reviser → Validator → 필요 Reviewer 재검토 → Gate
   → Final Chapter
   → 다음 Chapter
→ VISUAL RENDERING (deterministic VisualService)
→ FULL REPORT REVIEW
→ FINAL REVISION
→ PUBLICATION
```

성능보다 문서 품질·디버깅·재현성·구조 단순성·Chapter 간 일관성을 우선한다.

# 61. Planning Agent Structure (Final)

최종 Planning:

Source Intelligence
→ Report Strategist
→ Outline Architect
→ Outline Reviewer
→ deterministic Planning Gate
→ User Approval

현재 `OutlineDesigner`와 `ReportPlanner`는
실질적으로 같은 책임이므로 둘 다 유지하지 않는다.

실제 기능이 더 완성된 쪽을 기반으로
하나의 OutlineArchitect로 통합한다.

통합 완료 후 Wrapper/중복 구현은 삭제한다.

# 62. Persistence Canonical Decision (v1)

Schema Audit 결과:
`migrations_v2` 전체는 최종 ADK Architecture에 필수가 아니다.

Canonical Persistence = 현재 Runtime의 v1:

| 개념 | v1 테이블 | 비고 |
|------|-----------|------|
| Chapter 실행/저장 단위 | `sections` | DB 이름을 `chapters`로 재작성하지 않음 |
| Chapter revision/version | `section_versions` | |
| Chapter Review 연결 | `reviews.section_id` | |
| Resume | section 완료 skip 기반 | 이미 v1으로 동작 |
| Artifact | `artifacts` | 기존 table 활용; 평행 schema 금지 |

Backend Domain에서는 Chapter 개념을 사용할 수 있다.

Persistence Mapper가 기존 `section` 구조에 저장한다.

DB 이름이 `section`이라고 해서
Architecture 정리 목적으로 `chapters` 테이블을
다시 만들지 않는다.

# 63. migrations_v2 Retirement Policy

`migrations_v2` 전체 Cutover를 하지 않는다.

v2의 `chapters` / `chapter_versions` / `reviews.chapter_id` 등
v1과 의미적으로 중복되는 구조는
최종 Runtime으로 사용하지 않는다.

지금 즉시 DROP하지 않는다.

Retirement 순서:

1. Runtime reference 조사
2. Test reference 조사
3. Repository reference 조사
4. API dependence 조사
5. Frontend dependence 조사
6. startup/init schema dependence 조사
7. reference 0 확인
8. backup/rollback 확보
9. 그 이후 제거

v1/v2 장기 공존은 허용하지 않는다.

# 64. v2 Feature Cherry-pick Policy

v2 전체를 유지하지 않는다.

v2에만 존재하는 기능도
실제 제품 요구가 확인될 때만 별도로 검토한다.

## paragraph edit lock = EXISTING PRODUCT CONTRACT

Phase −1 Frontend/API Contract Audit 결과,
Frontend Production 화면이 실제로 다음을 사용한다.

- `PATCH /api/paragraphs/{paragraph_id}`
- body: `{ edit_state }`
- `USER_LOCKED` / `AI_EDITABLE` 등 상태를 UI 제어에 사용

따라서 paragraph edit lock은 LATER가 아니다.

최종 정책:

- paragraph edit lock = **EXISTING PRODUCT CONTRACT**
- Migration 중 Frontend API·동작·의미는 반드시 보존한다
- 이것이 `migrations_v2` 전체 유지를 의미하지는 않는다
- Persistence 구현 방식(v1/v2 정리)은 Phase 5에서 별도 판단한다
- Phase 0에서는 paragraph 관련 Production code / API / DB를 수정하지 않는다

현재 LATER (제품 계약이 아닌 추가 기능):

- paragraph evidence link
- quality snapshot

ADK Runtime에서 필요성이 확인될 때
최소 Schema만 별도 검토:

- agent run provenance

새로운 v2 전체 구조를 유지하기 위한 이유로
위 LATER 기능을 사용하지 않는다.
기존 제품 계약(paragraph edit lock)은 Compatibility Boundary로 보호한다.

# 65. Frontend Compatibility Policy

현재 Frontend가 완벽하지 않더라도
실제로 동작 중인 Frontend 기능을
Backend Architecture 리팩터링 때문에 깨뜨려서는 안 된다.

현재 Frontend ↔ Backend API Contract를
Compatibility Boundary로 취급한다.

Backend 내부(Agent / ADK / Service / Orchestration / Domain / Persistence)는
변경할 수 있다.

하지만 Frontend가 실제 사용하는:

- HTTP Method
- Route
- Request body
- Response body
- 주요 field
- enum 의미
- status code
- polling behavior

는 기본적으로 유지한다.

# 66. Domain vs API Contract Separation

Backend 내부 Domain 이름과
Frontend API 필드 이름이 동일할 필요는 없다.

예:

Internal Domain: `ChapterDraft`
현재 API: `SectionResponse`

Frontend가 `sections`를 소비한다면
Architecture 정리를 이유로 바로 `chapters`로 rename하지 않는다.

필요하면 Boundary Mapper를 사용한다.

```
Internal Chapter
  → mapper
Existing API DTO Section
  → Frontend (기존 Contract 유지)
```

# 67. Compatibility Adapter Rules

내부 구조를 변경하면서
기존 Frontend Contract 유지가 어려운 경우에만
Temporary Compatibility Adapter를 허용한다.

Adapter 요건:

- Business Logic을 가지지 않음
- 데이터 변환만 수행
- 대체 대상 명시
- 존재 이유 명시
- 제거 조건 명시
- 제거 Phase 명시

Compatibility Adapter를 두 번째 Runtime으로 만들지 않는다.

# 68. Frontend / API Contract Audit (필수 선행)

Production 코드 Migration을 시작하기 전에
Frontend/API Contract Audit을 먼저 수행한다.

추적:

Frontend Component
→ API Client
→ Method / Route
→ Request Schema
→ Response Schema
→ Backend Route
→ Service
→ Runtime

최소 기능 범위:

- 프로젝트
- Source Upload
- Source Processing
- Analysis
- Evidence
- Planning
- Outline
- Plan Approval
- Production
- Section/Chapter 조회
- Review
- Revision
- Visual
- Export
- Job/Progress

각 API 분류:

- `PUBLIC_FRONTEND_CONTRACT` — Migration 중 Compatibility 보호 대상
- `INTERNAL`
- `LEGACY_UNUSED`
- `UNKNOWN`

# 69. Frontend Regression Gate

각 Backend Migration Phase 완료 시
Backend test만 통과해서는 안 된다.

최소 확인:

Backend:
- unit
- integration
- startup
- health

Frontend:
- TypeScript
- frontend unit
- build
- 핵심 Playwright Read E2E

Contract:
- Route
- 주요 Response field
- Status semantics

Frontend가 깨지면 해당 Phase는 완료가 아니다.

# 70. Read E2E / Write E2E Separation

Architecture Migration 중
실제 사용자 Project를 자동 수정하지 않는다.

Read-only E2E:
자동 Playwright 가능.

Controlled Write E2E:
테스트 Project 사용을 우선한다.

실제 Project에서는
사용자가 직접 Action을 수행하고
Cursor는 결과를 검증한다.

# 71. Dead / Orphan Deletion Policy

Phase 0 삭제 후보(승인됨, 삭제 직전 재확인 필수):

- `orchestration/report_orchestrator.py`
- empty `agents/evidence_researcher`
- empty `agents/technical_writer`
- `frontend/public/legacy`
- orphan `__pycache__`

삭제 직전 필수:

- reference search
- import
- test
- frontend dependence
- runtime reachability

아직 자동 삭제하지 않음 (추가 확인 후):

- `evidence_refine`
- `citation_policy.md`
- `visual_policy.md`
- `source_service` alias
- blueprint schema
- `migrations` / `migrations_v2` (v2는 Phase 8 Retirement)

# 72. Final Migration Phases (−1 ~ 9)

각 Phase 공통 보고 형식:

- BEFORE Runtime
- CHANGE
- AFTER Runtime
- Frontend Contract
- MODIFY / MOVE / ADD / DELETE
- 남은 Legacy
- Rollback
- Backend Tests
- Frontend Tests
- E2E
- 완료 조건

ADD가 많고 DELETE/MERGE가 거의 없으면
설계를 재검토한다.

Cleanup은 각 Phase에 포함한다.
새 Runtime과 Legacy Runtime이 둘 다 활성이면 Phase 미완료다.

---

## Phase −1 — Baseline + Frontend/API Contract Audit

BEFORE:
현재 Runtime 동작. Production Migration 미시작.

CHANGE:
Contract Audit만 수행. Production 코드 변경 없음.
PUBLIC_FRONTEND_CONTRACT 목록 확정.
Baseline test/health 기록.

AFTER:
동일 Runtime. Audit 산출물만 추가.

Frontend Contract:
변경 없음. 보호 대상 목록화.

DELETE:
없음.

TEST:
기존 Backend unit/integration 스냅샷.
Frontend typecheck/build 스냅샷.
가능하면 Read E2E baseline.

Rollback:
문서만이면 N/A.

완료 조건:
Contract 분류표 존재.
핵심 화면→API→Runtime 추적 완료.
다음 Phase 착수 승인 가능.

---

## Phase 0 — Dead / Orphan Cleanup

BEFORE:
Dead orchestrator, empty agent pkgs, legacy HTML, orphan pycache 존재.

CHANGE:
Behavior Change = 0.
승인된 Dead/Orphan만 삭제.

AFTER:
동일 Runtime path.

Frontend Contract:
불변.

DELETE:
report_orchestrator, empty evidence_researcher/technical_writer,
frontend/public/legacy, orphan pycache
(삭제 직전 reference 재확인).

TEST:
Backend unit+integration+startup+health.
Frontend typecheck+build.
핵심 Read E2E.

Rollback:
삭제 전 commit/backup.

완료 조건:
Behavior 불변 확인.
reference 0.
Frontend Regression Gate PASS.

---

## Phase 1 — Corpus / ADK Dual Path 제거

BEFORE:
Corpus: direct agent path + adk_app scaffold(동일 httpx) Dual.

CHANGE:
단일 Corpus/Source Intelligence 실행 경로.
adk dual fork 제거 또는 adapter로 축소.

AFTER:
하나의 Corpus 실행 path.

Frontend Contract:
analyze API 불변.

DELETE:
중복 prompt_loader / unused adk corpus fork (검증 후).

TEST:
analysis pipeline tests + Frontend Regression Gate.

Rollback:
이전 path restore commit.

완료 조건:
Dual Path 없음.
Legacy corpus fork reference 0.

---

## Phase 2 — Planning Agent 중복 정리

BEFORE:
OutlineDesigner wraps ReportPlanner.

CHANGE:
Source Intelligence → Strategist → Outline Architect → Outline Reviewer → Gate → Approval.
단일 OutlineArchitect로 MERGE.

AFTER:
Planning 단일 체인.

Frontend Contract:
plans/outline/approve API 불변.

DELETE:
thin designer wrapper / 중복 prompt 연결.

TEST:
planning/outline gate + Frontend Regression Gate.

Rollback:
designer+planner 이전 호출 restore.

완료 조건:
Outline 책임 Owner 1개.
Wrapper reference 0.

---

## Phase 3 — Writing Contract 정리

BEFORE:
ChapterWriter contract/schema 불일치 가능.

CHANGE:
ChapterWriter contract, ChapterDraft canonical schema,
Context input, Citation reference contract 정리.
ProductionPipeline 최대한 유지.

AFTER:
동일 Writing loop, 계약 명확화.

Frontend Contract:
sections/editions API 불변.

DELETE:
중복 draft schema (MERGE 후).

TEST:
writer structured tests + Frontend Regression Gate.

Rollback:
이전 writer contract commit.

완료 조건:
Canonical ChapterDraft 1개.
API Section DTO mapping 유지.

---

## Phase 4 — Sequential Review / Revision

BEFORE:
Tech ∥ Editorial ThreadPool.
Silent offline fallback 가능.

CHANGE:
Technical → Editorial 순차.
Structured Review Issue.
Quality Gate.
Targeted Reviser.
Silent fallback 정리 (explicit offline mode only).

AFTER:
순차 Review/Revision.

Frontend Contract:
reviews/status 의미 유지. Response 주요 field 유지.

DELETE:
병렬 Reviewer 실행 경로.
암묵 offline 성공 처리.

TEST:
review_loop/quality_gate + Frontend Regression Gate.

Rollback:
병렬 loop commit restore.

완료 조건:
병렬 Reviewer 없음.
Silent ADK/LLM→offline COMPLETED 경로 없음.

---

## Phase 5 — Persistence 정리

BEFORE:
v1 sections Runtime + v2 optional/no-op 공존 가능.

CHANGE:
v1 Section Canonical 확정 반영.
v2 Runtime reference 제거(삭제 전 단계).
기존 `artifacts` table 활용 결정.
duplicate blueprint/state 정리.

AFTER:
Persistence SoT = v1.
Domain Chapter ↔ section mapper 문서화.

Frontend Contract:
sections 필드/route 유지.

DELETE:
v2를 Runtime에서 호출하는 코드 경로(테이블 DROP은 Phase 8).
unused blueprint duplicate.

TEST:
storage/resume tests + Frontend Regression Gate.

Rollback:
v2 optional detect 경로 restore.

완료 조건:
Runtime이 v2 chapters에 의존하지 않음.
artifacts 전략 문서화(기존 table KEEP 또는 최소 additive).

---

## Phase 6 — 실제 ADK Execution Migration

BEFORE:
Agent → direct model_providers/httpx.

CHANGE:
역할별 Vertical:
Agent → ADK execution → thin adapter → model_providers.
Frontend/API 동일.
Service/Orchestration 최대한 유지.
검증된 역할의 direct path 삭제.

AFTER:
Canonical agents가 ADK 실행 소유.
adk_app scaffold 축소.

Frontend Contract:
불변.

DELETE:
역할별 direct execution path.
불필요 adk_app scaffold.

TEST:
역할 contract + smoke + Frontend Regression Gate.

Rollback:
해당 역할 direct call restore.

완료 조건:
역할마다 Dual Path 없음.
model_providers 외 제2 Gateway 없음.

---

## Phase 7 — Citation / Visual / Publication 정리

BEFORE:
Citation 분산, Visual deterministic, policy prompt orphan 가능.

CHANGE:
Citation Owner 단일화.
VisualService 유지.
Visual Planner Agent 신규 추가는 기본 범위 아님.
Publication gate 정리.

AFTER:
Citation/Visual/Export 책임 명확.

Frontend Contract:
export/visual API 불변.

DELETE:
wire하지 않을 orphan policy prompt (확인 후).

TEST:
export/visual + Frontend Regression Gate.

Rollback:
이전 citation/visual path.

완료 조건:
내부 ID 최종 문서 비노출.
Visual Planner 미추가(요구 입증 전).

---

## Phase 8 — migrations_v2 Retirement

BEFORE:
migrations_v2 파일/부분 코드 잔존 가능.

CHANGE:
§63 Retirement 순서 전부.
reference 0 → tests → frontend → backup → rollback 확인 → 제거.

AFTER:
단일 v1 migration path.

Frontend Contract:
불변(이미 Phase 5에서 sections 유지).

DELETE:
migrations_v2 및 v2-only runtime/test glue.

TEST:
init_schema / migrations smoke + Frontend Regression Gate.

Rollback:
DB backup + migration files restore.

완료 조건:
v2 reference 0.
v1/v2 공존 없음.

---

## Phase 9 — Full E2E + Final Legacy Audit

BEFORE:
Phase −1~8 완료 상태.

CHANGE:
Full regression.
Final Legacy Audit (§56 기준).
문서/Runtime 일치 확인.

AFTER:
AGENTS.md Architecture = 실제 Runtime.

Frontend Contract:
보호 대상 전항 통과.

DELETE:
잔여 Dead/Orphan (감사 후).

TEST:
Backend full + Frontend full + Read E2E + Controlled Write E2E(테스트 Project).

Rollback:
release tag 기준.

완료 조건:
§56 Structural Completion Criteria 충족.
Dual Runtime 없음.
Frontend Regression Gate PASS.

# 73. Deletion Classification (Final)

### Phase 0 삭제 후보
- `backend/orchestration/report_orchestrator.py`
- `backend/agents/evidence_researcher/` (empty)
- `backend/agents/technical_writer/` (empty)
- `frontend/public/legacy/`
- orphan `__pycache__`

### 통합 후 삭제
- `outline_designer` wrapper (Phase 2 MERGE 후)
- ADK corpus dual fork / duplicate prompt_loader (Phase 1/6)
- Reviewer 병렬 실행 경로 (Phase 4)
- 역할별 direct LLM path (Phase 6, 검증 후)
- `adk_app` scaffold 잔여 (agents ADK 소유 후)

### 추가 확인 후 삭제
- `skills/retrieval/evidence_refine.py`
- `prompts/.../citation_policy.md`
- `prompts/.../visual_policy.md`
- `services/source_service.py` alias
- unused blueprint schema
- orphan policy/docs mismatch

### EXISTING PRODUCT CONTRACT (삭제·축소 금지; Persistence는 Phase 5)
- paragraph edit lock (`PATCH /api/paragraphs/{id}`, `edit_state`: USER_LOCKED / AI_EDITABLE 등)
  — Frontend Production UI가 사용 중. `migrations_v2` 전체 KEEP와 동일하지 않음.

### LATER (지금 삭제·도입 모두 보류)
- Visual Planner Agent
- paragraph evidence link / quality snapshot
- agent_runs provenance (필요 입증 시 최소 schema만)
- migrations_v2 DROP (Phase 8까지 보류)

# 74. Docs Alignment Rule

`docs/DESIGN.md`, `docs/FLOW.md`, `README.md` 등
설계·소개 문서가 현재 Runtime과 충돌하면
Runtime을 Source of Truth로 문서를 갱신한다.

특히 금지되는 문서 서술:

- `ReportOrchestrator`가 전역 워크플로 소유 (Dead)
- Reviewer 병렬이 최종 목표 Architecture
- EvidenceResearcher / TechnicalWriter empty stub를 현재 Agent로 소개
- v2 chapters를 필수 Persistence로 소개
- Visual Planner Agent를 현재 필수 단계로 소개

# 75. Open Architecture Decisions (사용자 선택 필요 시만)

현재 확정으로 충분한 항목은 재질문하지 않는다.

남아 있을 수 있는 선택(제품 요구 발생 시):

1. paragraph edit lock Persistence를 v1/v2 중 어디에 Canonical로 둘 것인가? (계약 자체는 EXISTING PRODUCT CONTRACT로 확정; 구현 정리는 Phase 5)
2. ADK run provenance를 DB에 남길 최소 범위는 무엇인가? (필요 입증 후)
3. Visual Planner Agent가 E2E에서 필요한가? (부족 입증 후)

파일명·구현 세부·Directory 취향은
사용자에게 묻지 않고 Runtime·Audit·본 문서를 따른다.
