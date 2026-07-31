#!/usr/bin/env python3
"""LLM smoke: ingest sample PDF → analyze → plan (strict, no offline fallback).

Usage:
  python scripts/llm_smoke.py
  python scripts/llm_smoke.py --model qwen3:8b
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="TAS LLM analyze/plan smoke")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "sample_mes.pdf",
    )
    parser.add_argument("--model", type=str, default=None, help="Override OLLAMA_MODEL")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Persist dir (default: temp)",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    os.environ["TAS_LLM_MODE"] = "llm"
    os.environ["TAS_LLM_STRICT"] = "1"

    if not args.pdf.is_file():
        from scripts.build_sample_pdf import build_sample_pdf

        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        build_sample_pdf(args.pdf)

    work = (args.workdir or Path(tempfile.mkdtemp(prefix="tas-llm-smoke-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    db = work / "tas.db"
    data = work / "data"
    (data / "projects").mkdir(parents=True, exist_ok=True)
    (data / "vector_indexes").mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["DATA_DIR"] = str(data)
    os.environ["VECTOR_INDEX_DIR"] = str(data / "vector_indexes")

    from backend import config

    config.settings = config.Settings(
        data_dir=data,
        database_url=f"sqlite:///{db}",
        vector_index_dir=data / "vector_indexes",
        llm_mode="llm",
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", config.settings.ollama_base_url),
        ollama_model=os.getenv("OLLAMA_MODEL", config.settings.ollama_model),
        ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600")),
    )

    from backend.model_providers.base import ollama_reachable, resolve_ollama_model

    ok, names = ollama_reachable()
    model = resolve_ollama_model("corpus_analyst")
    print(f"[llm_smoke] model={model} reachable={ok}")
    if not ok:
        print("[llm_smoke] FAIL: Ollama down")
        return 1
    if model not in names and not any(n.startswith(model) for n in names):
        print(f"[llm_smoke] FAIL: model missing. have={sorted(names)[:12]}…")
        return 2

    import sqlite3

    from backend.services.plan_service import PlanService
    from backend.services.project_service import ProjectService, SourceService
    from backend.storage.database import init_schema
    from backend.storage.file_store import FileStore

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode="llm")

    summary: dict = {"model": model, "workdir": str(work)}
    timings: dict[str, float] = {}

    project = projects.create("LLM smoke", f"pdf={args.pdf.name}")
    pid = project["project_id"]
    uploaded = sources.upload(pid, args.pdf.name, args.pdf.read_bytes())
    t0 = time.perf_counter()
    proc = sources.process(uploaded["source_id"])
    timings["ingest"] = time.perf_counter() - t0
    print(f"[llm_smoke] ingest pages={proc['page_count']} {timings['ingest']:.1f}s")

    t0 = time.perf_counter()
    analysis = plans.analyze(pid)
    timings["analyze"] = time.perf_counter() - t0
    print(
        f"[llm_smoke] analyze topic={analysis['main_topic']!r} "
        f"{timings['analyze']:.1f}s"
    )
    summary["main_topic"] = analysis["main_topic"]
    summary["technical_domain"] = analysis.get("technical_domain")

    t0 = time.perf_counter()
    plan = plans.generate_plan(pid)
    timings["plan"] = time.perf_counter() - t0
    print(
        f"[llm_smoke] plan title={plan['title']!r} "
        f"outline={plan['outline_count']} {timings['plan']:.1f}s"
    )
    summary["title"] = plan["title"]
    summary["outline_count"] = plan["outline_count"]
    summary["timings"] = timings

    out = work / "llm-smoke-summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[llm_smoke] summary → {out}")
    print("[llm_smoke] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
