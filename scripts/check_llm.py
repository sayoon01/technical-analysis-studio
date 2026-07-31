#!/usr/bin/env python3
"""Check Ollama reachability and configured model availability.

Usage:
  python scripts/check_llm.py
  OLLAMA_MODEL=gemma4:31b python scripts/check_llm.py --ping
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Ollama / TAS LLM config")
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Run a tiny JSON chat round-trip against the configured model",
    )
    args = parser.parse_args()

    from backend import config
    from backend.model_providers.base import (
        LlmError,
        call_ollama_json,
        ollama_reachable,
        resolve_ollama_model,
    )

    ok, names = ollama_reachable()
    model = resolve_ollama_model("corpus_analyst")
    print(f"OLLAMA_BASE_URL={config.settings.ollama_base_url}")
    print(f"TAS_LLM_MODE={config.settings.llm_mode}")
    print(f"resolved_model={model}")
    print(f"reachable={ok}")
    if not ok:
        print("[check_llm] FAIL: Ollama not reachable")
        return 1

    print(f"model_installed={model in names}")
    if model not in names:
        print("[check_llm] FAIL: model not in ollama list")
        print("available:")
        for n in sorted(names):
            print(f"  - {n}")
        return 2

    if args.ping:
        t0 = time.perf_counter()
        try:
            data = call_ollama_json(
                "Return JSON only.",
                'Return {"ok": true, "echo": "tas"} as JSON.',
                model=model,
                temperature=0.0,
                timeout=120.0,
            )
        except LlmError as e:
            print(f"[check_llm] FAIL ping: {e}")
            return 3
        elapsed = time.perf_counter() - t0
        print(f"ping_seconds={elapsed:.2f}")
        print(f"ping_response={json.dumps(data, ensure_ascii=False)[:200]}")
        if not isinstance(data, dict):
            print("[check_llm] FAIL: non-object JSON")
            return 3

    print("[check_llm] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
