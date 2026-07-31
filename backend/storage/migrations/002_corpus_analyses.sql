-- Phase 2: persist corpus analysis payloads

CREATE TABLE IF NOT EXISTS corpus_analyses (
    analysis_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    snapshot_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_corpus_analyses_project
ON corpus_analyses(project_id, created_at);
