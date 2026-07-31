# 테스트 설계

## Unit
- page type classification heuristics
- quality_gate blockers
- state_machine transitions
- citation / metric parsers

## Ingestion
- PDF page order
- text layer vs OCR fallback
- reading order / bbox
- diagram node·edge extraction hooks
- metric definition + measurement capture

## Golden (첨부 발표자료 PDF)
기대 연결 (페이지 정확):
- 문제: 인프라 노후, 실적 누락, 수기, 계량 미연계 → ~p.12
- 구성: 클라우드 MES, 본사, 공장, PDA, VPN → ~p.14
- 성과: +8% / -60% / -33% / +24% → ~p.16–17

도메인 키워드를 **테스트 fixture**에만 두고, 제품 코드 분기에는 넣지 않는다.

## Generality
MES / NPU·GPU / EMG / ALD / 수질 / 배터리 — 코드 변경 없이 제목·목차·Evidence·Visual·결론이 달라져야 함.

## Edition safety
V1에 무근거 “운영비 45% 감소” 삽입 → V2에서 상속 금지(삭제 또는 미확인).

## Impact
납기 준수율만 보강된 새 자료 → 해당 절 PARTIAL_REWRITE, 타 장 KEEP.
