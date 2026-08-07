"""HTTP contract test fixtures (Phase 0.5). Production code unchanged."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


HARD_PHASES = frozenset({"analyzing", "planning", "producing", "reviewing"})


def _rebind_backend_settings(monkeypatch, new_settings) -> None:
    """Patch Settings on every already-imported backend module."""
    import backend.config as config

    monkeypatch.setattr(config, "settings", new_settings)
    for name, mod in list(sys.modules.items()):
        if not name.startswith("backend"):
            continue
        obj = getattr(mod, "settings", None)
        if obj is not None and type(obj).__name__ == "Settings":
            monkeypatch.setattr(mod, "settings", new_settings)


def _reset_request_state() -> None:
    from backend.api import deps
    from backend.services import job_status

    deps._local.conn = None
    job_status._jobs.clear()
    job_status._locks.clear()


@pytest.fixture()
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated SQLite + data dir for TestClient (does not touch data/tas.db)."""
    db = tmp_path / "contract.db"
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("VECTOR_INDEX_DIR", str(data / "vector_indexes"))
    monkeypatch.setenv("TAS_LLM_MODE", "offline")

    from backend import config

    new_settings = config.Settings(
        data_dir=data,
        database_url=f"sqlite:///{db}",
        vector_index_dir=data / "vector_indexes",
        llm_mode="offline",
    )
    _rebind_backend_settings(monkeypatch, new_settings)
    _reset_request_state()

    from backend.main import app

    with TestClient(app) as client:
        yield {
            "client": client,
            "db": db,
            "data": data,
            "tmp_path": tmp_path,
        }

    _reset_request_state()


@pytest.fixture()
def client(api_env):
    return api_env["client"]


def assert_hard_fields(payload: dict, fields: list[str], *, ctx: str = "") -> None:
    missing = [f for f in fields if f not in payload]
    assert not missing, f"{ctx} missing HARD fields: {missing}; keys={sorted(payload)}"


def build_sample_pdf_bytes(tmp_path: Path) -> bytes:
    from scripts.build_sample_pdf import build_sample_pdf

    path = build_sample_pdf(tmp_path / "contract-sample.pdf")
    return path.read_bytes()
