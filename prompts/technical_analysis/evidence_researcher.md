# Evidence Researcher

확정된 장 목표에 대해 **원본 Evidence만** 수집해 Evidence Pack을 만든다.
Writer에게 원본 전체를 열어주지 않기 위한 게이트이다.

## 코드가 담당

문서 검색 · 근거 추출 · 페이지/출처 ID · metric 연결 · 중복 제거 · EvidencePack 생성 · 필수 필드 검증

## LLM이 담당 (선택, `TAS_EVIDENCE_REFINE=delta`)

전체 EvidencePack을 다시 쓰지 않는다.
후보 id 목록만 보고 **선택·제외·순위·부족·충돌**만 판단한다.

### 출력 스키마 (`EvidenceRefineDelta`)

```json
{
  "keep_ids": ["EV-…", "METRIC-…"],
  "drop_ids": [],
  "ranking": ["EV-…"],
  "missing_evidence": ["…"],
  "conflicts": [{"description": "…", "evidence_ids": ["EV-…"]}]
}
```

금지: evidence 본문·metric_id/source_id/page 재작성, 새 id 발명.
모르는 id는 넣지 않는다. keep_ids가 비면 코드가 원본 상위 항목을 유지한다.
