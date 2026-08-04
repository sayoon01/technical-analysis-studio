"""Deterministic outline quality gate."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.domain.report_plan import ReportPlan

FORBIDDEN_TOP_LEVEL = {"PDA", "VPN", "User PC", "MES System", "Hourly production volume"}


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def validate_outline(plan: ReportPlan) -> GateResult:
    reasons: list[str] = []
    top = [n for n in plan.outline if n.level == 1]
    if not (5 <= len(top) <= 8):
        reasons.append(f"top-level chapters must be 5..8 (got {len(top)})")

    for n in top:
        t = (n.title or "").strip()
        if t in FORBIDDEN_TOP_LEVEL:
            reasons.append(f"forbidden top-level heading: {t}")
        if "..." in t:
            reasons.append(f"ellipsis heading not allowed: {t}")
        if re.search(r"(SRC-|EVD-|P-INFRA-|P-PROB-|<!--)", t):
            reasons.append(f"internal marker in heading: {t}")
        if len(t) < 2:
            reasons.append("empty/too-short top-level heading")
        if _looks_fragment(t):
            reasons.append(f"sentence fragment heading: {t}")
        if not (n.objective or "").strip():
            reasons.append(f"missing objective on top-level: {t}")

    return GateResult(passed=not reasons, reasons=reasons)


def _looks_fragment(title: str) -> bool:
    s = title.strip()
    # Very rough fragment detector for OCR-y junk.
    if any(ch in s for ch in ["(", ")", ":", ";"]) and len(s) < 6:
        return True
    if re.fullmatch(r"[A-Za-z0-9 _/\-]+", s) and " " not in s and len(s) <= 3:
        return True
    return False
