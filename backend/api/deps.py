"""Shared FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from backend.services.edition_service import EditionService
from backend.services.export_service import ExportService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.review_service import ReviewService
from backend.storage.database import connect, init_schema
from backend.storage.file_store import FileStore


@lru_cache(maxsize=1)
def get_connection() -> sqlite3.Connection:
    conn = connect()
    init_schema(conn)
    return conn


def get_project_service() -> ProjectService:
    return ProjectService(get_connection())


def get_source_service() -> SourceService:
    return SourceService(get_connection(), FileStore())


def get_plan_service() -> PlanService:
    return PlanService(get_connection())


def get_edition_service() -> EditionService:
    return EditionService(get_connection())


def get_review_service() -> ReviewService:
    return ReviewService(get_connection())


def get_export_service() -> ExportService:
    return ExportService(get_connection())
