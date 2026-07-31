-- Phase 3: evidence packs + paragraph locations helper index

CREATE TABLE IF NOT EXISTS evidence_packs (
    evidence_pack_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_packs_section
ON evidence_packs(section_id);
