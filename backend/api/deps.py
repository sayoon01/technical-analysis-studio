"""Shared FastAPI dependencies.

SQLite connections are thread-local: long LLM requests and concurrent
status polls must not share one Connection (causes InterfaceError).
"""

from __future__ import annotations

import sqlite3
import threading

from backend.services.edition_service import EditionService
from backend.services.export_service import ExportService
from backend.services.plan_service import PlanService
from backend.services.project_service import ProjectService, SourceService
from backend.services.review_service import ReviewService
from backend.storage.database import connect
from backend.storage.file_store import FileStore

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
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
