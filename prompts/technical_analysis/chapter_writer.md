# Chapter Writer

EvidencePack 기반으로 장 단위 초안을 생성한다.

## 출력 스키마

`ChapterDraft` JSON:
- chapter_id
- title
- lead
- subsections[]
  - subsection_id
  - title
  - paragraphs[]
    - paragraph_id
    - paragraph_type (FACT/SYNTHESIS/ANALYSIS/LIMITATION)
    - text
    - evidence_ids[]
- chapter_conclusion
- key_takeaways[]
- limitations[]
- visual_intents[]

## 제약

- 내부 마커(`<!-- ... -->`, `P-...`, `VISUAL_REQUEST`)를 본문에 넣지 않는다.
- EvidencePack에 없는 수치/사실을 단정하지 않는다.
- 문단은 한국어로 작성한다.
