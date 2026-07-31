"""Claim-evidence ledger and side-car builders."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def write_claim_ledger(path: Path, claims: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "claims"
    ws.append(
        [
            "claim_id",
            "section_id",
            "statement",
            "claim_type",
            "verification_status",
            "evidence_ids",
            "source_pages",
        ]
    )
    for c in claims:
        evidence = c.get("evidence") or []
        eids = ",".join(e.get("evidence_id", "") for e in evidence)
        pages = ",".join(
            f"{e.get('source_id')}:p.{e.get('page')}" for e in evidence
        )
        ws.append(
            [
                c.get("claim_id"),
                c.get("section_id"),
                c.get("statement"),
                c.get("claim_type"),
                c.get("verification_status"),
                eids,
                pages,
            ]
        )
    wb.save(str(path))
    return path
