from __future__ import annotations

import sqlite3

from backend.domain.enums import VisualType
from backend.domain.visual import VisualRequest
from backend.services.visual_service import VisualRenderService, VisualValidationService
from backend.storage.database import init_schema


def test_visual_validator_rejects_placeholder_tokens():
    validator = VisualValidationService()
    req = VisualRequest(
        visual_id="VIS-1",
        section_id="SEC-1",
        visual_type=VisualType.PROCESS_FLOW,
        title="흐름",
        purpose="테스트",
        render_spec={"steps": ["시작", "처리", "종료"]},
    )
    ok, reason = validator.validate(req)
    assert not ok
    assert reason


def test_render_service_skips_invalid_and_renders_valid(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "v.db"))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    renderer = VisualRenderService(conn)
    valid = VisualRequest(
        visual_id="VIS-TABLE",
        section_id="SEC-1",
        visual_type=VisualType.COMPARISON_TABLE,
        title="표",
        purpose="지표 요약",
        render_spec={"headers": ["h1"], "rows": [["v1"]]},
    )
    invalid = VisualRequest(
        visual_id="VIS-BAD",
        section_id="SEC-1",
        visual_type=VisualType.PROCESS_FLOW,
        title="흐름",
        purpose="테스트",
        render_spec={"steps": ["시작", "처리", "종료"]},
    )
    out = renderer.render_all([valid, invalid], tmp_path / "visuals")
    assert any(k.startswith("VIS-TABLE") for k in out["rendered"])
    assert all(req["visual_id"] != "VIS-BAD" for req in out["requests"])
