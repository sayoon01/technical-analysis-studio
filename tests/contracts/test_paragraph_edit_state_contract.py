"""Paragraph edit_state contract (EXISTING PRODUCT CONTRACT).

Uses current Runtime path (ChapterRepository paragraphs when v2 tables exist).
Does NOT revive migrations_v2 as production SoT — test fixture only.
"""

from __future__ import annotations

from backend.domain.chapter import ChapterDraft, DraftParagraph, SubsectionDraft
from backend.storage.database import connect
from backend.storage.edition_repository import ChapterRepository
from tests.contracts.conftest import assert_hard_fields


ALLOWED_EDIT_STATES = frozenset({"USER_LOCKED", "AI_EDITABLE"})

# Minimal paragraph tables matching current Runtime ChapterRepository path.
# Applies only chapter/paragraph DDL onto the contract v1 DB — does not run
# full migrations_v2 cutover (Phase 5/8 concern).
_PARAGRAPH_RUNTIME_DDL = """
CREATE TABLE IF NOT EXISTS chapters (
  chapter_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  chapter_key TEXT NOT NULL,
  title TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapter_versions (
  chapter_version_id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  body_markdown TEXT NOT NULL,
  summary TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(chapter_id, revision),
  FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS paragraphs (
  paragraph_id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  subsection_key TEXT,
  paragraph_type TEXT,
  text TEXT NOT NULL,
  order_index INTEGER NOT NULL DEFAULT 0,
  edit_state TEXT NOT NULL DEFAULT 'AI_EDITABLE',
  FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS paragraph_evidence_links (
  paragraph_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (paragraph_id, evidence_id),
  FOREIGN KEY (paragraph_id) REFERENCES paragraphs(paragraph_id) ON DELETE CASCADE
);
"""


def _seed_paragraph(db_path, paragraph_id: str = "PAR-CONTRACT-1") -> str:
    conn = connect(db_path)
    try:
        conn.executescript(_PARAGRAPH_RUNTIME_DDL)
        conn.commit()
        repo = ChapterRepository(conn)
        assert repo.has_v2_tables()
        draft = ChapterDraft(
            chapter_id="CH-CONTRACT",
            title="계약 문단",
            lead="",
            subsections=[
                SubsectionDraft(
                    subsection_id="SUB-1",
                    title="소절",
                    paragraphs=[
                        DraftParagraph(
                            paragraph_id=paragraph_id,
                            paragraph_type="FACT",
                            text="초기 문단",
                            evidence_ids=[],
                        )
                    ],
                )
            ],
        )
        repo.save_chapter_draft(
            edition_id="ED-CONTRACT",
            section_id="SEC-CONTRACT",
            order_index=1,
            chapter_key="NODE-CONTRACT",
            draft=draft,
            body_markdown="초기 문단",
        )
    finally:
        conn.close()
    return paragraph_id


def test_paragraph_edit_state_request_body_and_round_trip(client, api_env):
    from backend.api import deps

    paragraph_id = _seed_paragraph(api_env["db"])
    deps._local.conn = None

    # Request contract: { "edit_state": ... }
    r = client.patch(
        f"/api/paragraphs/{paragraph_id}",
        json={"edit_state": "USER_LOCKED"},
    )
    assert r.status_code == 200, r.text
    locked = r.json()
    assert_hard_fields(locked, ["paragraph_id", "edit_state", "text"], ctx="lock")
    assert locked["edit_state"] == "USER_LOCKED"
    assert locked["edit_state"] in ALLOWED_EDIT_STATES

    r = client.patch(
        f"/api/paragraphs/{paragraph_id}",
        json={"edit_state": "AI_EDITABLE"},
    )
    assert r.status_code == 200, r.text
    unlocked = r.json()
    assert unlocked["edit_state"] == "AI_EDITABLE"
    assert unlocked["edit_state"] in ALLOWED_EDIT_STATES

    # Toggle round-trip as ProductionPage does
    r = client.patch(
        f"/api/paragraphs/{paragraph_id}",
        json={"edit_state": "USER_LOCKED"},
    )
    assert r.status_code == 200
    assert r.json()["edit_state"] == "USER_LOCKED"


def test_paragraph_patch_route_accepts_edit_state_field(client, api_env):
    """Freeze PATCH /api/paragraphs/{id} body field name used by Frontend client."""
    from backend.api import deps

    paragraph_id = _seed_paragraph(api_env["db"], "PAR-CONTRACT-2")
    deps._local.conn = None

    # Wrong field name should not silently succeed as lock — body requires edit_state default
    r = client.patch(f"/api/paragraphs/{paragraph_id}", json={})
    # Default edit_state on API is USER_LOCKED
    assert r.status_code == 200, r.text
    assert r.json()["edit_state"] == "USER_LOCKED"

    r = client.patch(
        f"/api/paragraphs/{paragraph_id}",
        json={"edit_state": "AI_EDITABLE", "text": "사용자 수정"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["edit_state"] == "AI_EDITABLE"
    assert body["text"] == "사용자 수정"
