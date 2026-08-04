PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS report_editions (
  edition_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  edition_number INTEGER NOT NULL,
  parent_edition_id TEXT,
  corpus_snapshot_id TEXT,
  outline_id TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publication_documents (
  publication_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  title TEXT NOT NULL,
  subtitle TEXT,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (edition_id) REFERENCES report_editions(edition_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exports (
  export_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  format TEXT NOT NULL,
  file_path TEXT NOT NULL,
  status TEXT NOT NULL,
  readiness_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (edition_id) REFERENCES report_editions(edition_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  edition_id TEXT,
  workflow_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_outputs (
  output_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  schema_name TEXT NOT NULL,
  output_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_editions_project ON report_editions(project_id, edition_number);
CREATE INDEX IF NOT EXISTS idx_exports_edition ON exports(edition_id, format);
