PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS visual_specs (
  visual_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  chapter_id TEXT,
  visual_type TEXT NOT NULL,
  title TEXT NOT NULL,
  caption TEXT,
  purpose TEXT,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  source_pages_json TEXT NOT NULL DEFAULT '[]',
  render_spec_json TEXT NOT NULL DEFAULT '{}',
  validation_status TEXT NOT NULL DEFAULT 'PENDING',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visual_assets (
  asset_id TEXT PRIMARY KEY,
  visual_id TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  file_path TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (visual_id) REFERENCES visual_specs(visual_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_visual_specs_edition ON visual_specs(edition_id);
