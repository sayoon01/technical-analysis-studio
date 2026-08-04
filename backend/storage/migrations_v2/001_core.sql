PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  stage TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  role TEXT NOT NULL,
  filename TEXT NOT NULL,
  mime_type TEXT,
  status TEXT NOT NULL,
  checksum TEXT,
  page_count INTEGER DEFAULT 0,
  storage_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_pages (
  page_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  page_type TEXT,
  visual_role TEXT,
  image_path TEXT,
  text TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(source_id, page_number),
  FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_blocks (
  block_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  block_type TEXT NOT NULL,
  bbox TEXT,
  text TEXT,
  confidence REAL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_pages_source ON source_pages(source_id, page_number);
CREATE INDEX IF NOT EXISTS idx_blocks_source_page ON content_blocks(source_id, page_number);
