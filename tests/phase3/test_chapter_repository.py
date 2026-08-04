from __future__ import annotations

from pathlib import Path

from backend.domain.chapter import ChapterDraft, DraftParagraph, SubsectionDraft
from backend.storage.database import connect, init_schema_v2
from backend.storage.edition_repository import ChapterRepository


def _draft(text: str, paragraph_id: str, evidence_ids: list[str]) -> ChapterDraft:
    return ChapterDraft(
        chapter_id="CH-001",
        title="테스트 장",
        lead="리드",
        subsections=[
            SubsectionDraft(
                subsection_id="SUB-001",
                title="소절",
                paragraphs=[
                    DraftParagraph(
                        paragraph_id=paragraph_id,
                        paragraph_type="FACT",
                        text=text,
                        evidence_ids=evidence_ids,
                    )
                ],
            )
        ],
    )


def test_save_chapter_draft_persists_chapter_and_paragraphs(tmp_path: Path):
    db = tmp_path / "tas-v2.db"
    conn = connect(db)
    init_schema_v2(conn)
    repo = ChapterRepository(conn)

    repo.save_chapter_draft(
        edition_id="ED-1",
        section_id="SEC-1",
        order_index=1,
        chapter_key="NODE-1",
        draft=_draft("첫 문단", "PAR-1", ["E-1", "E-2"]),
        body_markdown="## 테스트 장\n\n첫 문단\n",
        summary="initial",
    )

    c = conn.execute("SELECT * FROM chapters WHERE chapter_id = 'CH-001'").fetchone()
    assert c is not None
    assert c["chapter_key"] == "NODE-1"
    assert c["order_index"] == 1
    p = conn.execute("SELECT * FROM paragraphs WHERE chapter_id = 'CH-001'").fetchall()
    assert len(p) == 1
    links = conn.execute(
        "SELECT evidence_id FROM paragraph_evidence_links WHERE paragraph_id = 'PAR-1' ORDER BY evidence_id"
    ).fetchall()
    assert [r["evidence_id"] for r in links] == ["E-1", "E-2"]
    v = conn.execute("SELECT COUNT(*) AS c FROM chapter_versions WHERE chapter_id = 'CH-001'").fetchone()
    assert int(v["c"]) == 1


def test_save_chapter_draft_replaces_paragraphs_and_increments_revision(tmp_path: Path):
    db = tmp_path / "tas-v2.db"
    conn = connect(db)
    init_schema_v2(conn)
    repo = ChapterRepository(conn)

    repo.save_chapter_draft(
        edition_id="ED-1",
        section_id="SEC-1",
        order_index=1,
        chapter_key="NODE-1",
        draft=_draft("첫 문단", "PAR-1", ["E-1"]),
        body_markdown="v1",
    )
    repo.save_chapter_draft(
        edition_id="ED-1",
        section_id="SEC-1",
        order_index=2,
        chapter_key="NODE-1",
        draft=_draft("둘째 문단", "PAR-2", ["E-9"]),
        body_markdown="v2",
    )

    p = conn.execute("SELECT paragraph_id, text FROM paragraphs WHERE chapter_id = 'CH-001'").fetchall()
    assert len(p) == 1
    assert p[0]["paragraph_id"] == "PAR-2"
    assert p[0]["text"] == "둘째 문단"
    v = conn.execute(
        "SELECT MAX(revision) AS r, COUNT(*) AS c FROM chapter_versions WHERE chapter_id = 'CH-001'"
    ).fetchone()
    assert int(v["r"]) == 2
    assert int(v["c"]) == 2


def test_save_chapter_draft_preserves_user_locked_paragraph(tmp_path: Path):
    db = tmp_path / "tas-v2.db"
    conn = connect(db)
    init_schema_v2(conn)
    repo = ChapterRepository(conn)

    repo.save_chapter_draft(
        edition_id="ED-1",
        section_id="SEC-1",
        order_index=1,
        chapter_key="NODE-1",
        draft=_draft("초안 문단", "PAR-LOCK", ["E-1"]),
        body_markdown="v1",
    )
    repo.set_paragraph_edit_state("PAR-LOCK", "USER_LOCKED", text="사용자 고정 문단")
    repo.save_chapter_draft(
        edition_id="ED-2",
        section_id="SEC-2",
        order_index=1,
        chapter_key="NODE-1",
        draft=_draft("AI가 다시 쓴 문단", "PAR-LOCK", ["E-1"]),
        body_markdown="v2",
    )

    row = conn.execute(
        "SELECT text, edit_state FROM paragraphs WHERE paragraph_id = 'PAR-LOCK'"
    ).fetchone()
    assert row is not None
    assert row["text"] == "사용자 고정 문단"
    assert row["edit_state"] == "USER_LOCKED"
