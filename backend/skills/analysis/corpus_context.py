"""Build corpus context packs for Analyst/Planner (no LLM)."""

from __future__ import annotations

import sqlite3
from typing import Any


def build_corpus_context(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    sources = conn.execute(
        """
        SELECT source_id, filename, role, status, page_count
        FROM sources
        WHERE project_id = ? AND role = 'EVIDENCE_SOURCE' AND status = 'READY'
        ORDER BY created_at
        """,
        (project_id,),
    ).fetchall()
    source_ids = [r["source_id"] for r in sources]

    pages: list[dict] = []
    for sid in source_ids:
        page_rows = conn.execute(
            """
            SELECT page_number, page_type, text_layer_available
            FROM source_pages WHERE source_id = ? ORDER BY page_number
            """,
            (sid,),
        ).fetchall()
        for pr in page_rows:
            blocks = conn.execute(
                """
                SELECT text, block_type, reading_order
                FROM content_blocks
                WHERE source_id = ? AND page_number = ?
                ORDER BY reading_order
                """,
                (sid, pr["page_number"]),
            ).fetchall()
            text = "\n".join(
                b["text"] for b in blocks if b["block_type"] != "IMAGE" and b["text"]
            )
            pages.append(
                {
                    "source_id": sid,
                    "page_number": pr["page_number"],
                    "page_type": pr["page_type"],
                    "text": text[:4000],
                }
            )

    metrics = []
    if source_ids:
        ph = ",".join("?" * len(source_ids))
        metrics = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT metric_id, name, result_value, change_value, change_unit,
                       direction, page_number, source_id, measurement_method,
                       confidence
                FROM metric_facts WHERE source_id IN ({ph})
                ORDER BY page_number
                """,
                source_ids,
            ).fetchall()
        ]

    # Compact digest for LLM (cap pages)
    digest_pages = []
    for p in pages:
        if not p["text"].strip() and p["page_type"] == "TEXT":
            continue
        digest_pages.append(
            {
                "source_id": p["source_id"],
                "page": p["page_number"],
                "type": p["page_type"],
                "text": p["text"][:1200],
            }
        )

    compact_metrics = _compact_metrics(metrics)
    format_notes = role_text_digest(conn, project_id, "FORMAT_REFERENCE")
    previous_notes = role_text_digest(conn, project_id, "PREVIOUS_EDITION")

    return {
        "project_id": project_id,
        "sources": [dict(s) for s in sources],
        "page_count": len(pages),
        "page_type_counts": _count_types(pages),
        "metrics": metrics,
        "pages": digest_pages[:40],
        # Smaller pack for LLM calls (full `pages`/`metrics` kept for offline)
        "llm_pack": build_llm_pack(digest_pages, compact_metrics, sources),
        # Non-evidence roles: style/layout only — never fact sources
        "format_notes": format_notes,
        "previous_edition_notes": previous_notes,
    }


def role_text_digest(
    conn: sqlite3.Connection,
    project_id: str,
    role: str,
    *,
    max_chars: int = 4000,
) -> str:
    """Extract text from READY sources of a given role (FORMAT / PREVIOUS)."""
    rows = conn.execute(
        """
        SELECT source_id, filename
        FROM sources
        WHERE project_id = ? AND role = ? AND status = 'READY'
        ORDER BY created_at
        """,
        (project_id, role),
    ).fetchall()
    if not rows:
        return ""
    parts: list[str] = []
    budget = max_chars
    for src in rows:
        if budget <= 0:
            break
        parts.append(f"[{src['filename']}]")
        blocks = conn.execute(
            """
            SELECT text FROM content_blocks
            WHERE source_id = ? AND block_type != 'IMAGE'
            ORDER BY page_number, reading_order
            LIMIT 80
            """,
            (src["source_id"],),
        ).fetchall()
        text = "\n".join(
            (b["text"] or "").strip() for b in blocks if (b["text"] or "").strip()
        )
        text = text[:budget]
        parts.append(text)
        budget -= len(text)
    return "\n".join(parts).strip()


# Back-compat alias used by pipelines
_role_text_digest = role_text_digest


def build_llm_pack(
    digest_pages: list[dict],
    metrics: list[dict],
    sources: list[Any],
    *,
    max_pages: int = 18,
    per_page_chars: int = 450,
) -> dict[str, Any]:
    """Shrink context so 31B models finish within timeout."""
    # Prefer non-TEXT / denser pages first, keep order stable within type
    ranked = sorted(
        digest_pages,
        key=lambda p: (
            0 if p.get("type") in {"DIAGRAM", "CHART", "MIXED", "TABLE"} else 1,
            p.get("page") or 0,
        ),
    )
    pages_out = []
    for p in ranked[:max_pages]:
        text = _dedupe_lines((p.get("text") or "")[: per_page_chars * 2])
        pages_out.append(
            {
                "page": p.get("page"),
                "type": p.get("type"),
                "text": text[:per_page_chars],
            }
        )
    pages_out.sort(key=lambda p: p.get("page") or 0)
    return {
        "sources": [
            {"source_id": dict(s)["source_id"], "filename": dict(s)["filename"]}
            for s in sources
        ],
        "metrics": metrics[:24],
        "pages": pages_out,
    }


def _compact_metrics(metrics: list[dict]) -> list[dict]:
    out = []
    for m in metrics:
        name = str(m.get("name") or "").strip()
        if not name or len(name) > 80:
            continue
        has_change = m.get("change_value") is not None and (
            m.get("change_unit") == "%" or m.get("direction")
        )
        has_absolute = m.get("result_value") is not None and m.get("change_unit")
        if not (has_change or has_absolute):
            continue
        out.append(
            {
                "name": name[:60],
                "result_value": m.get("result_value"),
                "change_value": m.get("change_value"),
                "change_unit": m.get("change_unit"),
                "direction": m.get("direction"),
                "page": m.get("page_number"),
            }
        )
    return out[:24]


def _dedupe_lines(text: str) -> str:
    seen: set[str] = set()
    lines = []
    for ln in text.splitlines():
        key = "".join(ln.split()).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(ln.strip())
    return "\n".join(lines)


def _count_types(pages: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in pages:
        out[p["page_type"]] = out.get(p["page_type"], 0) + 1
    return out
