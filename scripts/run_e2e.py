#!/usr/bin/env python3
"""End-to-end run: ingest → analyze → plan → produce → review → export → V2.

Usage:
  TAS_LLM_MODE=offline python scripts/run_e2e.py
  TAS_LLM_MODE=llm python scripts/run_e2e.py --llm
  python scripts/run_e2e.py --llm --strict --skip-v2
  python scripts/run_e2e.py --pdf path/to/doc.pdf --addendum path/to/extra.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="TAS end-to-end pipeline")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "sample_mes.pdf",
        help="Primary evidence PDF",
    )
    parser.add_argument(
        "--addendum",
        type=Path,
        default=None,
        help="Optional extra PDF for V2 impact (default: built-in delivery addendum)",
    )
    parser.add_argument("--llm", action="store_true", help="Force TAS_LLM_MODE=llm")
    parser.add_argument("--offline", action="store_true", help="Force TAS_LLM_MODE=offline")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if review all_passed=False; with --llm also set TAS_LLM_STRICT=1",
    )
    parser.add_argument(
        "--skip-v2", action="store_true", help="Stop after V1 export"
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Persist data dir (default: temp)",
    )
    args = parser.parse_args()

    if args.llm:
        os.environ["TAS_LLM_MODE"] = "llm"
    elif args.offline:
        os.environ["TAS_LLM_MODE"] = "offline"
    os.environ.setdefault("TAS_LLM_MODE", "offline")

    if args.strict and os.environ["TAS_LLM_MODE"] == "llm":
        os.environ["TAS_LLM_STRICT"] = "1"

    if not args.pdf.is_file():
        # build sample if missing
        from scripts.build_sample_pdf import build_sample_pdf

        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        build_sample_pdf(args.pdf)
        print(f"[e2e] built sample pdf → {args.pdf}")

    work = args.workdir or Path(tempfile.mkdtemp(prefix="tas-e2e-"))
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    db = work / "tas.db"
    data = work / "data"
    (data / "projects").mkdir(parents=True, exist_ok=True)
    (data / "vector_indexes").mkdir(parents=True, exist_ok=True)
    (data / "exports").mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["DATA_DIR"] = str(data)
    os.environ["VECTOR_INDEX_DIR"] = str(data / "vector_indexes")

    from backend import config

    config.settings = config.Settings(
        data_dir=data,
        database_url=f"sqlite:///{db}",
        vector_index_dir=data / "vector_indexes",
        llm_mode=os.environ["TAS_LLM_MODE"],
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", config.settings.ollama_base_url),
        ollama_model=os.getenv("OLLAMA_MODEL", config.settings.ollama_model),
        ollama_timeout=float(
            os.getenv("OLLAMA_TIMEOUT_SECONDS", str(config.settings.ollama_timeout))
        ),
    )

    import sqlite3

    from backend.services.edition_service import EditionService
    from backend.services.export_service import ExportService
    from backend.services.plan_service import PlanService
    from backend.services.project_service import ProjectService, SourceService
    from backend.services.review_service import ReviewService
    from backend.storage.database import init_schema
    from backend.storage.file_store import FileStore

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    store = FileStore(root=data / "projects")
    llm_mode = os.environ["TAS_LLM_MODE"]

    projects = ProjectService(conn)
    sources = SourceService(conn, store)
    plans = PlanService(conn, llm_mode=llm_mode)
    editions = EditionService(
        conn, llm_mode=llm_mode, vector_root=data / "vector_indexes"
    )
    reviews = ReviewService(conn, llm_mode=llm_mode)
    exports = ExportService(conn)

    summary: dict = {
        "llm_mode": llm_mode,
        "strict": bool(args.strict),
        "workdir": str(work),
        "ollama_model": config.settings.ollama_model,
    }
    exit_code = 0

    print(f"[e2e] mode={llm_mode} workdir={work}")
    project = projects.create("E2E 기술분석", f"pdf={args.pdf.name}")
    pid = project["project_id"]
    summary["project_id"] = pid
    print(f"[e2e] project {pid}")

    uploaded = sources.upload(pid, args.pdf.name, args.pdf.read_bytes())
    print(f"[e2e] uploaded {uploaded['source_id']}")
    proc = sources.process(uploaded["source_id"])
    print(f"[e2e] processed pages={proc['page_count']} blocks={proc['block_count']}")

    analysis = plans.analyze(pid)
    print(f"[e2e] analysis topic={analysis['main_topic']!r}")
    summary["main_topic"] = analysis["main_topic"]

    plan = plans.generate_plan(pid)
    print(f"[e2e] plan title={plan['title']!r} outline={plan['outline_count']}")
    summary["title"] = plan["title"]
    summary["outline_count"] = plan["outline_count"]

    approved = plans.approve_outline(pid)
    print(f"[e2e] outline approved → {approved['stage']}")

    v1 = editions.produce(pid)
    print(
        f"[e2e] V1 edition={v1['edition_id']} sections={len(v1['sections'])}"
    )
    summary["v1_edition_id"] = v1["edition_id"]

    rev = reviews.review_edition(v1["edition_id"])
    print(
        f"[e2e] review all_passed={rev['all_passed']} stage={rev['stage']}"
    )
    summary["review"] = {
        "all_passed": rev["all_passed"],
        "manual_review": rev.get("manual_review"),
        "stage": rev["stage"],
    }
    if args.strict and not rev.get("all_passed"):
        print("[e2e] STRICT: review did not all_pass")
        exit_code = 10

    exp = exports.export_edition(v1["edition_id"])
    print(f"[e2e] export zip={exp['files']['zip']}")
    print(f"[e2e]   md={exp['files']['markdown']}")
    print(f"[e2e]   visuals unrendered={exp['visuals']['unrendered']}")
    summary["export"] = exp["files"]

    if not args.skip_v2:
        if args.addendum and args.addendum.is_file():
            add_path = args.addendum
        else:
            from scripts.build_delivery_addendum import build_delivery_addendum

            add_path = work / "delivery_addendum.pdf"
            build_delivery_addendum(add_path)

        extra = sources.upload(pid, add_path.name, add_path.read_bytes())
        sources.process(extra["source_id"])
        print(f"[e2e] addendum {extra['source_id']}")

        preview = editions.preview_impact(
            pid, v1["edition_id"], new_source_ids=[extra["source_id"]]
        )
        decisions = [i["decision"] for i in preview["impacts"]]
        print(f"[e2e] impact decisions={sorted(set(decisions))}")

        v2 = editions.improve(
            pid, v1["edition_id"], new_source_ids=[extra["source_id"]]
        )
        print(
            f"[e2e] V2 edition={v2['edition_id']} "
            f"kept={v2['kept_count']} rewritten={v2['rewritten_count']}"
        )
        summary["v2"] = {
            "edition_id": v2["edition_id"],
            "kept_count": v2["kept_count"],
            "rewritten_count": v2["rewritten_count"],
        }

        diff = editions.diff_editions(v1["edition_id"], v2["edition_id"])
        modified = sum(1 for s in diff["sections"] if s["change"] == "MODIFIED")
        print(f"[e2e] diff modified_sections={modified}")
        summary["diff_modified_sections"] = modified

    out_json = work / "e2e-summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[e2e] summary → {out_json}")

    latest = ROOT / "data" / "e2e-runs" / "latest"
    latest.parent.mkdir(parents=True, exist_ok=True)
    if latest.exists() or latest.is_symlink():
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        else:
            shutil.rmtree(latest)
    try:
        latest.symlink_to(work, target_is_directory=True)
    except OSError:
        shutil.copytree(work, latest, dirs_exist_ok=True)
    print(f"[e2e] latest → {latest}")

    if exit_code:
        print(f"[e2e] DONE with errors exit={exit_code}")
    else:
        print("[e2e] DONE")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
