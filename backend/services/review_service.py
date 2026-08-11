"""Review application service.

Edition review business logic lives in ReviewLoop only.
Sync HTTP and background start share that same loop.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from typing import Any

from backend.model_providers.base import LlmError
from backend.orchestration.review_loop import ReviewLoop, is_edition_retry_skip
from backend.services.job_status import (
    finish_job,
    lock_for,
    set_job,
    update_job,
)
from backend.storage.database import connect
from backend.storage.edition_repository import EditionRepository, SectionRepository
from backend.storage.review_repository import ReviewRepository

logger = logging.getLogger(__name__)


def _safe_review_error(
    exc: BaseException, *, failed_step: str | None = None
) -> str:
    """User-safe failure text — no traceback / prompts / secrets.

    Validation messages are stage-specific when ``failed_step`` is known
    (technical_review / editorial_review / revising).
    """
    if isinstance(exc, LlmError):
        text = str(exc).splitlines()[0].strip()
        if len(text) > 240:
            text = text[:240] + "…"
        lower = text.lower()
        for needle in ("password", "authorization", "api_key", "secret", "token="):
            if needle in lower:
                return "Review model request failed"
        if "validation" in lower or "structured generation" in lower:
            step = (failed_step or "").strip().lower()
            if step in {"revising", "revision", "revise"}:
                return "Revision model output validation failed"
            if step in {"editorial_review", "editorial"}:
                return "Editorial review model output validation failed"
            if step in {"technical_review", "technical"}:
                return "Technical review model output validation failed"
            return "Review model output validation failed"
        if "timed out" in lower:
            return "Review model request timed out"
        return f"Review model request failed: {text}"
    name = type(exc).__name__
    return f"Review job failed ({name})"


class ReviewService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
        on_progress=None,
    ) -> None:
        self.conn = conn
        self.llm_mode = llm_mode
        self.loop = ReviewLoop(conn, llm_mode=llm_mode, on_progress=on_progress)
        self.reviews = ReviewRepository(conn)
        self.sections = SectionRepository(conn)
        self.editions = EditionRepository(conn)

    def review_edition(self, edition_id: str) -> dict:
        """Synchronous edition review (existing PUBLIC contract). Blocks until done."""
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        project_id = edition["project_id"]
        lock = lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("A job is already running for this project")
        set_job(project_id, "reviewing")
        try:
            return self.loop.run_edition(edition_id)
        finally:
            finish_job(project_id)
            lock.release()

    def start_edition_review(self, edition_id: str) -> dict:
        """Start edition review in a background thread; return immediately.

        Worker creates its own SQLite connection / ReviewService / ReviewLoop.
        Does not reuse this request-thread connection.
        """
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        project_id = edition["project_id"]
        sections = self.sections.list_for_edition(edition_id)
        sections = self.sections.list_for_edition(edition_id)
        total = sum(
            1
            for s in sections
            if not is_edition_retry_skip(s.get("status") or "")
        )

        lock = lock_for(project_id)
        if not lock.acquire(blocking=False):
            raise ValueError("A job is already running for this project")

        set_job(
            project_id,
            "reviewing",
            current_step="starting",
            completed_sections=0,
            total_sections=total,
            current_section=None,
            current_section_title=None,
        )

        llm_mode = self.llm_mode

        def worker() -> None:
            worker_conn: sqlite3.Connection | None = None
            failed_step = "starting"
            failed_section: str | None = None
            try:
                # Fresh connection owned by this thread (check_same_thread=True).
                worker_conn = connect()

                def on_progress(info: dict[str, Any]) -> None:
                    nonlocal failed_step, failed_section
                    if info.get("current_step"):
                        failed_step = str(info["current_step"])
                    if info.get("current_section"):
                        failed_section = str(info["current_section"])
                    update_job(project_id, **info)

                svc = ReviewService(
                    worker_conn,
                    llm_mode=llm_mode,
                    on_progress=on_progress,
                )
                # Same canonical ReviewLoop class; not a second runtime.
                result = svc.loop.run_edition(edition_id)
                finish_job(
                    project_id,
                    result={
                        "edition_id": result.get("edition_id"),
                        "all_passed": result.get("all_passed"),
                        "manual_review": result.get("manual_review"),
                        "stage": result.get("stage"),
                    },
                )
            except Exception as exc:
                logger.exception(
                    "background edition review failed edition=%s project=%s",
                    edition_id,
                    project_id,
                )
                finish_job(
                    project_id,
                    error=_safe_review_error(exc, failed_step=failed_step),
                    failed_step=failed_step,
                    failed_section=failed_section,
                )
            finally:
                if worker_conn is not None:
                    try:
                        worker_conn.close()
                    except Exception:
                        logger.exception("failed closing review worker connection")
                lock.release()

        try:
            thread = threading.Thread(
                target=worker,
                name=f"review-edition-{edition_id}",
                daemon=True,
            )
            thread.start()
        except Exception:
            finish_job(project_id, error="Failed to start review worker")
            lock.release()
            raise

        return {
            "accepted": True,
            "phase": "reviewing",
            "edition_id": edition_id,
            "project_id": project_id,
            "total_sections": total,
        }

    def review_section(self, section_id: str) -> dict:
        return self.loop.run_section(section_id)

    def review_full_report(self, edition_id: str) -> dict:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        return self.loop.run_full_report(edition_id)

    def list_section_reviews(self, section_id: str) -> list[dict]:
        if not self.sections.get(section_id):
            raise KeyError(section_id)
        return self.reviews.list_for_section(section_id)

    def open_issues(self, section_id: str) -> list[dict]:
        if not self.sections.get(section_id):
            raise KeyError(section_id)
        return self.reviews.open_issues(section_id)

    def list_full_report_reviews(self, edition_id: str) -> list[dict]:
        edition = self.editions.get(edition_id)
        if not edition:
            raise KeyError(edition_id)
        return self.reviews.list_full_report_reviews(edition_id)
