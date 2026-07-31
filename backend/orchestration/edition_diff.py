"""Compare two report editions (outline, sections, claims, metrics mentions)."""

from __future__ import annotations

import re
import sqlite3

from backend.storage.edition_repository import ClaimRepository, SectionRepository


class EditionDiffer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.sections = SectionRepository(conn)
        self.claims = ClaimRepository(conn)

    def diff(self, left_edition_id: str, right_edition_id: str) -> dict:
        left = self.sections.list_for_edition(left_edition_id)
        right = self.sections.list_for_edition(right_edition_id)

        left_by_title = {s["title"]: s for s in left}
        right_by_title = {s["title"]: s for s in right}

        added_titles = sorted(set(right_by_title) - set(left_by_title))
        removed_titles = sorted(set(left_by_title) - set(right_by_title))
        common = sorted(set(left_by_title) & set(right_by_title))

        section_changes = []
        for title in common:
            a = left_by_title[title]
            b = right_by_title[title]
            a_md = a.get("content_markdown") or ""
            b_md = b.get("content_markdown") or ""
            if a_md.strip() == b_md.strip():
                change = "UNCHANGED"
            else:
                change = "MODIFIED"
            section_changes.append(
                {
                    "title": title,
                    "left_section_id": a["section_id"],
                    "right_section_id": b["section_id"],
                    "change": change,
                    "left_len": len(a_md),
                    "right_len": len(b_md),
                    "paragraph_diff": _paragraph_diff(a_md, b_md),
                }
            )

        left_claims = []
        right_claims = []
        for s in left:
            left_claims.extend(self.claims.list_for_section(s["section_id"]))
        for s in right:
            right_claims.extend(self.claims.list_for_section(s["section_id"]))

        left_stmts = {c["statement"] for c in left_claims}
        right_stmts = {c["statement"] for c in right_claims}

        left_nums = _all_pcts("\n".join(s.get("content_markdown") or "" for s in left))
        right_nums = _all_pcts("\n".join(s.get("content_markdown") or "" for s in right))

        return {
            "left_edition_id": left_edition_id,
            "right_edition_id": right_edition_id,
            "outline": {
                "added_sections": added_titles,
                "removed_sections": removed_titles,
                "common_sections": common,
            },
            "sections": section_changes,
            "claims": {
                "added": sorted(right_stmts - left_stmts)[:50],
                "removed": sorted(left_stmts - right_stmts)[:50],
            },
            "metrics_mentioned": {
                "left": sorted(left_nums),
                "right": sorted(right_nums),
                "added": sorted(right_nums - left_nums),
                "removed": sorted(left_nums - right_nums),
            },
        }


def _paragraph_diff(a: str, b: str) -> dict:
    pa = set(_paras(a))
    pb = set(_paras(b))
    return {
        "added": sorted(pb - pa)[:20],
        "removed": sorted(pa - pb)[:20],
    }


def _paras(md: str) -> list[str]:
    chunks = re.split(r"\n\s*\n", md or "")
    out = []
    for c in chunks:
        t = re.sub(r"<!--.*?-->", "", c, flags=re.S)
        t = re.sub(r"^#+\s*", "", t.strip())
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 20:
            out.append(t[:200])
    return out


def _all_pcts(text: str) -> set[float]:
    return {float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text or "")}
