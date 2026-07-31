"""Strip unsupported inherited claims; light-edit parent section for V2 KEEP/LIGHT_EDIT."""

from __future__ import annotations

import re

from backend.domain.evidence import EvidencePack
from backend.skills.analysis.section_writer import extract_citations
from backend.skills.analysis.review_offline import review_technical_offline


def scrub_inherited_section(
    markdown: str,
    *,
    pack: EvidencePack,
    section_id: str,
) -> str:
    """Remove numeric/factual claims not supported by current EvidencePack."""
    content = markdown
    # Drop percentage sentences not in pack
    pack_nums = {
        float(m.change_value)
        for m in pack.metrics
        if m.change_value is not None
    }
    for item in list(pack.definitions) + list(pack.supporting_facts):
        for n in re.findall(r"(\d+(?:\.\d+)?)\s*%", item.statement):
            pack_nums.add(float(n))

    parts = re.split(r"(?<=\n\n)", content)
    kept = []
    for p in parts:
        pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", p)]
        if pcts and any(v not in pack_nums and not _near(v, pack_nums) for v in pcts):
            # drop unsupported numeric paragraph
            continue
        # Drop citations not in pack
        for cite in extract_citations(p):
            ok = any(
                cite["source_id"] == it.source_id and cite["page"] == it.page
                for it in list(pack.definitions) + list(pack.supporting_facts)
            ) or any(
                cite["source_id"] == m.source_id and cite["page"] == m.page_number
                for m in pack.metrics
            )
            if not ok:
                p = p.replace(cite["span"], "")
        kept.append(p)

    scrubbed = "".join(kept)
    scrubbed = re.sub(r"\n{3,}", "\n\n", scrubbed).strip() + "\n"

    # Final gate: if still mismatched, fall back to empty marker
    tech = review_technical_offline(
        section_id=section_id, markdown=scrubbed, pack=pack, claims=[]
    )
    if tech.numeric_mismatch_count > 0:
        # remove remaining bad % lines
        lines = []
        for line in scrubbed.splitlines(keepends=True):
            bad = False
            for v in re.findall(r"(\d+(?:\.\d+)?)\s*%", line):
                if float(v) not in pack_nums and not _near(float(v), pack_nums):
                    bad = True
            if not bad:
                lines.append(line)
        scrubbed = "".join(lines)
    return scrubbed


def _near(v: float, nums: set[float], tol: float = 0.01) -> bool:
    return any(abs(v - n) <= tol for n in nums)
