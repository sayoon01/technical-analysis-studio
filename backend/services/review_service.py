"""Review application service."""

from __future__ import annotations

import sqlite3

from backend.orchestration.review_loop import ReviewLoop
from backend.storage.edition_repository import SectionRepository
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

    def review_edition(self, edition_id: str) -> dict:
        return self.loop.run_edition(edition_id)

    def review_section(self, section_id: str) -> dict:
        return self.loop.run_section(section_id)

    def list_section_reviews(self, section_id: str) -> list[dict]:
        if not self.sections.get(section_id):
            raise KeyError(section_id)
        return self.reviews.list_for_section(section_id)

    def open_issues(self, section_id: str) -> list[dict]:
        if not self.sections.get(section_id):
            raise KeyError(section_id)
        return self.reviews.open_issues(section_id)
