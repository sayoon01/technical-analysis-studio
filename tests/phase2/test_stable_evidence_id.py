from __future__ import annotations

from backend.skills.retrieval.evidence_builder import make_evidence_id


def test_make_evidence_id_is_stable():
    sid = "SRC-ABC"
    page = 16
    blocks = ["BLK-2", "BLK-1"]
    statement = "시간당 생산량 8% 증가"

    a = make_evidence_id(sid, page, blocks, statement)
    b = make_evidence_id(sid, page, list(reversed(blocks)), statement + "   ")
    assert a == b
    assert a.startswith("EVD-")
