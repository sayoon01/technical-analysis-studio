PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS content_groups (
  group_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  group_type TEXT NOT NULL,
  bbox TEXT,
  title TEXT,
  block_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS corpus_snapshots (
  corpus_snapshot_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS corpus_snapshot_sources (
  corpus_snapshot_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  PRIMARY KEY (corpus_snapshot_id, source_id),
  FOREIGN KEY (corpus_snapshot_id) REFERENCES corpus_snapshots(corpus_snapshot_id) ON DELETE CASCADE,
  FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence_records (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  block_ids_json TEXT NOT NULL DEFAULT '[]',
  statement TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
  FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_groups_source_page ON content_groups(source_id, page_number);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence_records(project_id);
