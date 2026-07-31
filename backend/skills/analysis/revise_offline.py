"""Offline reviser: fix only flagged issues using EvidencePack."""

from __future__ import annotations

import re

from backend.domain.evidence import EvidencePack
from backend.domain.review import EditorialReview, RevisionResult, TechnicalReview
from backend.skills.analysis.section_writer import extract_citations, write_section_offline


def revise_section_offline(
    *,
    title: str,
    objective: str,
    markdown: str,
    pack: EvidencePack,
    technical: TechnicalReview,
    editorial: EditorialReview,
    revision: int,
) -> RevisionResult:
    content = markdown
    changes: list[dict] = []
    resolved: list[str] = []

    # Drop paragraphs with unsupported numeric claims not in pack
    pack_numbers = set()
    for m in pack.metrics:
        if m.change_value is not None:
            pack_numbers.add(float(m.change_value))

    for issue in technical.issues:
        if issue.issue_type == "NUMERIC_MISMATCH":
            # Remove sentences containing the bad number
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", issue.description)
            if m:
                bad = m.group(1)
                new_content, n = _remove_sentences_with_number(content, bad)
                if n:
                    content = new_content
                    changes.append(
                        {
                            "change_type": "REMOVE_NUMERIC",
                            "reason": issue.description,
                            "issue_id": issue.issue_id,
                        }
                    )
                    resolved.append(issue.issue_id)
        elif issue.issue_type == "UNSUPPORTED_CLAIM":
            # Remove or soften: delete the described claim snippet if present
            snippet = issue.description.split(":", 1)[-1].strip()[:40]
            if snippet and snippet in content:
                content = content.replace(snippet, "")
                changes.append(
                    {
                        "change_type": "LIMIT_SCOPE",
                        "reason": issue.description,
                        "issue_id": issue.issue_id,
                    }
                )
                resolved.append(issue.issue_id)
            else:
                # Rebuild from pack (safer)
                content = write_section_offline(
                    title=title, objective=objective, pack=pack
                )
                changes.append(
                    {
                        "change_type": "REWRITE_FROM_PACK",
                        "reason": "unsupported claims cleared via pack rewrite",
                        "issue_id": issue.issue_id,
                    }
                )
                resolved.append(issue.issue_id)
                break
        elif issue.issue_type == "CITATION_MISMATCH":
            # Strip bad citations
            for cite in extract_citations(content):
                key_ok = any(
                    cite["source_id"] == item.source_id and cite["page"] == item.page
                    for item in list(pack.definitions) + list(pack.supporting_facts)
                ) or any(
                    cite["source_id"] == m.source_id and cite["page"] == m.page_number
                    for m in pack.metrics
                )
                if not key_ok:
                    content = content.replace(cite["span"], "")
                    changes.append(
                        {
                            "change_type": "STRIP_CITATION",
                            "reason": issue.description,
                            "issue_id": issue.issue_id,
                        }
                    )
            resolved.append(issue.issue_id)

    for issue in editorial.issues:
        if issue.issue_type == "PROMOTIONAL_LANGUAGE":
            for phrase in ("최고의", "혁신적인 솔루션", "완벽한", "업계 최고", "반드시 도입", "세계 최고"):
                if phrase in content:
                    content = content.replace(phrase, "자료에서 확인된")
                    changes.append(
                        {
                            "change_type": "NEUTRALIZE_PROMO",
                            "reason": issue.description,
                            "issue_id": issue.issue_id,
                        }
                    )
            resolved.append(issue.issue_id)

    # Collapse excess blank lines
    content = re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"

    # If still empty-ish, rewrite from pack
    if len(content) < 80:
        content = write_section_offline(title=title, objective=objective, pack=pack)
        changes.append({"change_type": "REWRITE_FROM_PACK", "reason": "content too short after fixes"})

    return RevisionResult(
        revision=revision,
        updated_content=content,
        changes=changes,
        resolved_issue_ids=list(dict.fromkeys(resolved)),
    )


def _remove_sentences_with_number(text: str, number: str) -> tuple[str, int]:
    parts = re.split(r"(?<=[.。\n])\s*", text)
    kept = []
    removed = 0
    for p in parts:
        if re.search(rf"{re.escape(number)}\s*%", p):
            removed += 1
            continue
        kept.append(p)
    return ("\n".join(k for k in kept if k.strip()) + "\n", removed)
