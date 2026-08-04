from __future__ import annotations

import json
from pathlib import Path

import yaml


def _rules() -> dict:
    path = Path("tests/golden/mes_case/expected_publication_rules.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_golden_fixture_contract_exists():
    assert Path("tests/golden/mes_case/expected_metrics.json").exists()
    assert Path("tests/golden/mes_case/expected_source.json").exists()
    assert Path("tests/golden/mes_case/expected_structure.json").exists()
    assert Path("tests/golden/mes_case/expected_outline_rules.yaml").exists()
    assert Path("tests/golden/mes_case/expected_visual_rules.yaml").exists()
    assert Path("tests/golden/mes_case/expected_publication_rules.yaml").exists()


def test_publication_forbidden_marker_contract():
    rules = _rules()
    forbidden = rules["forbidden"]
    assert "<!--" in forbidden
    assert "VISUAL_REQUEST" in forbidden
    assert "SRC-" in forbidden
    assert "EVD-" in forbidden


def test_required_metric_contract():
    metrics = _load_json("tests/golden/mes_case/expected_metrics.json")[
        "performance_metrics"
    ]
    assert len(metrics) == 4
    names = {m["name"] for m in metrics}
    assert names == {"시간당 생산량", "출하 클레임", "재공재고", "납기 준수율"}
