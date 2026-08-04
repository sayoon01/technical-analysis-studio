"""Review application service."""

from __future__ import annotations

import sqlite3

from backend.orchestration.review_loop import ReviewLoop
from backend.services.job_status import lock_for, set_job
from backend.storage.edition_repository import EditionRepository, SectionRepository
from backend.storage.review_repository import ReviewRepository


class ReviewService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        llm_mode: str | None = None,
    ) -> None:
        self.conn = conn
        self.loop = ReviewLoop(conn, llm_mode=llm_mode)
        self.reviews = ReviewRepository(conn)
        self.sections = SectionRepository(conn)
        self.editions = EditionRepository(conn)

    def review_edition(self, edition_id: str) -> dict:
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
            set_job(project_id, None)
            lock.release()

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
