# Technical Analysis Studio
<img width="1348" height="1179" alt="image" src="https://github.com/user-attachments/assets/0728a465-6c43-4dc2-a41b-476f31d4136c" />

**전문가 기술분석서** 생성 시스템 (Ollama agents + deterministic skills).  

설계 문서: [docs/DESIGN.md](docs/DESIGN.md) · [docs/API.md](docs/API.md) · [docs/UI.md](docs/UI.md) · [docs/TESTING.md](docs/TESTING.md)

## 한 줄 요약

업로드한 기술자료만으로 페이지 유형·표·수치·다이어그램까지 구조화하고,  
자료에 맞는 목차를 설계·승인한 뒤, 근거 기반 작성·검토·Edition 개선까지 수행합니다.  
주제(MES, NPU 등)를 코드에 하드코딩하지 않습니다.

## 핵심 원칙

1. **사실 근거** = `EVIDENCE_SOURCE` 원본만  
2. **수정 기반** = 이전 Edition (업로드 `PREVIOUS_EDITION`은 문체·구조 참고만)  
3. **형식 참고** = `FORMAT_REFERENCE` 양식 (사실로 쓰지 않음)  
4. 파싱·OCR·검색·품질 게이트·렌더링 = deterministic 코드  
5. LLM = Ollama(향후 ADK execution) Agents; 전역 워크플로는 `backend/orchestration/*`가 소유  
   (`ReportOrchestrator` Dead — 사용하지 않음). Architecture SoT: [AGENTS.md](AGENTS.md)

## 현재 상태

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 설계·스키마·config | ✅ |
| 1 | Ingestion·FTS5·Vector (Ollama embeddings) | ✅ |
| 2 | Analyst·Planner·목차 승인 | ✅ |
| 3 | Evidence·Writer | ✅ |
| 4 | Review·Quality Gate | ✅ |
| 5 | Visuals·Export | ✅ |
| 6 | Impact·Edition V2 | ✅ |

### 로컬 실행

```bash
pip install -e ".[dev]"
cp .env.example .env
python scripts/init_db.py
uvicorn backend.main:app --reload
```

프론트엔드 (별도 터미널):

```bash
cd frontend
npm install
npm run dev
# http://127.0.0.1:5173  — /api 는 Vite가 :8000 으로 프록시
```

E2E (오프라인 기본):

```bash
TAS_LLM_MODE=offline python scripts/run_e2e.py
# 요약은 data/e2e-runs/latest/
# 검토 미통과 시 실패: python scripts/run_e2e.py --strict
```

### LLM (Ollama) 실가동

```bash
# 1) 서버·모델 확인 (+ JSON ping)
python scripts/check_llm.py --ping

# 2) analyze→plan 스모크 (폴백 금지, 시간 측정)
python scripts/llm_smoke.py
# 다른 모델: OLLAMA_MODEL=qwen3:8b python scripts/llm_smoke.py

# 3) 전체 E2E (LLM, 폴백 금지, V1만)
python scripts/run_e2e.py --llm --strict --skip-v2
```

| env | 의미 |
|-----|------|
| `TAS_LLM_MODE=llm\|offline` | Agent LLM 사용 / deterministic |
| `OLLAMA_MODEL` | 실제 Ollama 태그 (env가 `models.yaml`보다 우선) |
| `EMBEDDING_MODEL` | Ollama 임베딩 모델 (기본 `bge-m3`) |
| `TAS_EMBEDDING_MODE=ollama\|hash` | 임베딩 백엔드 |
| `TAS_LLM_STRICT=1` | LLM 실패 시 offline 폴백 금지 |

테스트:

```bash
TAS_LLM_MODE=offline python -m pytest tests/ -q
```

흐름: … → export → 추가 자료 업로드 → `POST .../impact/preview` → `POST .../editions` `{parent_edition_id}` (영향 장만 재작성) → `GET .../diff/{other}`

## 디렉터리

```
backend/
  api/ · services/ · orchestration/ · agents/ · skills/
  domain/ · storage/ (v1 Canonical) · model_providers/
  adk_app/          # TEMP Migration Adapter only
frontend/    React/Vite (기존 API Contract = Compatibility Boundary)
prompts/     Agent instructions (외부 파일)
config/      models · ingestion · retrieval · review · …
docs/        DESIGN · FLOW · API · UI · TESTING
AGENTS.md    Architecture SoT + Migration Phases −1~9
```

지원 업로드: PDF · DOCX · MD/TXT · PPTX · XLSX/CSV · **HWP/HWPX**

## 로컬 (Phase 1 이후)

```bash
cp .env.example .env
# uv/pip sync 후
python scripts/init_db.py
```

## 금지 사항

```python
# 금지
if "MES" in topic:
    outline = MES_OUTLINE
```

목차·제목·지표 유형은 항상 Corpus → Planner 파이프라인에서 생성합니다.
