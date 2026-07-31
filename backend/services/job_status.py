"""In-memory project job status (analyze / plan / produce / review).

Process-local; survives across request threads. Not persisted to SQLite.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_guard = threading.Lock()

PHASE_LABELS = {
    "analyzing": "자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다",
    "planning": "목차 생성 중 (Ollama) — 수 분 걸릴 수 있습니다",
    "producing": "보고서 작성 중 (Ollama) — 장 수에 따라 오래 걸릴 수 있습니다",
    "reviewing": "검토 중 (Ollama) — 수 분 걸릴 수 있습니다",
}


def lock_for(project_id: str) -> threading.Lock:
    with _locks_guard:
        if project_id not in _locks:
            _locks[project_id] = threading.Lock()
        return _locks[project_id]


def set_job(project_id: str, phase: str | None) -> None:
    with _jobs_guard:
        if phase is None:
            _jobs.pop(project_id, None)
            return
        prev = _jobs.get(project_id) or {}
        _jobs[project_id] = {
            "phase": phase,
            "label": PHASE_LABELS.get(phase, phase),
            "started_at": prev.get("started_at")
            or datetime.now(timezone.utc).isoformat(),
        }


def get_job(project_id: str) -> dict | None:
    with _jobs_guard:
        job = _jobs.get(project_id)
        return dict(job) if job else None
