"""In-memory project job status (analyze / plan / produce / review).

Process-local; survives across request threads within one process.
Not persisted to SQLite.

LIMITATIONS (Phase 4.2 — intentional, not hidden):
- Safe across browser navigation / HTTP disconnect in the same process.
- NOT safe across process crash, server restart, uvicorn --reload, or
  multi-worker ownership. Full Edition Review E2E should use non-reload
  uvicorn for the duration of the job.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_jobs: dict[str, dict] = {}
_jobs_guard = threading.Lock()
# Retained after busy clears so Frontend can show last failure / summary.
_outcomes: dict[str, dict] = {}

PHASE_LABELS = {
    "analyzing": "자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다",
    "planning": "목차 생성 중 (Ollama) — 수 분 걸릴 수 있습니다",
    "producing": "보고서 작성 중 (Ollama) — 장 수에 따라 오래 걸릴 수 있습니다",
    "reviewing": "검토 중 (Ollama) — 수 분 걸릴 수 있습니다",
}

STEP_LABELS = {
    "starting": "검토 시작",
    "validating": "초안 검증 중",
    "technical_review": "기술 검토 중",
    "editorial_review": "편집 검토 중",
    "aggregating": "이슈 집계 중",
    "quality_gate": "품질 게이트",
    "revising": "수정 중",
    "full_report": "전체 보고서 검토 중",
    "completed": "검토 완료",
}

_PROGRESS_KEYS = (
    "current_section",
    "current_section_title",
    "current_step",
    "completed_sections",
    "total_sections",
)


def lock_for(project_id: str) -> threading.Lock:
    with _locks_guard:
        if project_id not in _locks:
            _locks[project_id] = threading.Lock()
        return _locks[project_id]


def set_job(project_id: str, phase: str | None, **fields: Any) -> None:
    """Set or clear the live in-process job.

    phase=None clears the live job (busy → false) but does not erase
    a previously recorded outcome unless a new job starts later.
    """
    with _jobs_guard:
        if phase is None:
            _jobs.pop(project_id, None)
            return
        # New job supersedes prior failure/summary projection.
        _outcomes.pop(project_id, None)
        prev = _jobs.get(project_id) or {}
        job: dict[str, Any] = {
            "phase": phase,
            "label": PHASE_LABELS.get(phase, phase),
            "started_at": prev.get("started_at")
            or datetime.now(timezone.utc).isoformat(),
        }
        for key in _PROGRESS_KEYS:
            if key in fields:
                job[key] = fields[key]
            elif key in prev:
                job[key] = prev[key]
        step = job.get("current_step")
        if step and step in STEP_LABELS and phase == "reviewing":
            job["label"] = STEP_LABELS[step]
        _jobs[project_id] = job


def update_job(project_id: str, **fields: Any) -> None:
    """Merge progress into an existing live job. No-op if no job."""
    with _jobs_guard:
        job = _jobs.get(project_id)
        if not job:
            return
        for key, value in fields.items():
            if value is not None:
                job[key] = value
        step = job.get("current_step")
        if step and step in STEP_LABELS and job.get("phase") == "reviewing":
            job["label"] = STEP_LABELS[step]
        elif job.get("phase") in PHASE_LABELS and "label" not in fields:
            # keep step label if set; otherwise phase default
            if not step:
                job["label"] = PHASE_LABELS[job["phase"]]


def finish_job(
    project_id: str,
    *,
    error: str | None = None,
    failed_step: str | None = None,
    failed_section: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """Clear live busy job and optionally retain a safe outcome for polling."""
    with _jobs_guard:
        _jobs.pop(project_id, None)
        outcome: dict[str, Any] = {
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            outcome["error"] = error
        if failed_step:
            outcome["failed_step"] = failed_step
        if failed_section:
            outcome["failed_section"] = failed_section
        if result is not None:
            outcome["result"] = result
        if error or result is not None:
            _outcomes[project_id] = outcome
        else:
            _outcomes.pop(project_id, None)


def get_job(project_id: str) -> dict | None:
    with _jobs_guard:
        job = _jobs.get(project_id)
        return dict(job) if job else None


def get_job_outcome(project_id: str) -> dict | None:
    with _jobs_guard:
        out = _outcomes.get(project_id)
        return dict(out) if out else None


def clear_job_outcome(project_id: str) -> None:
    with _jobs_guard:
        _outcomes.pop(project_id, None)
