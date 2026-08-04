PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS report_blueprints (
  blueprint_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  outline_id TEXT NOT NULL,
  approved_title TEXT NOT NULL,
  approved_subtitle TEXT,
  central_thesis TEXT,
  executive_summary_points_json TEXT NOT NULL DEFAULT '[]',
  terminology_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
  FOREIGN KEY (outline_id) REFERENCES outlines(outline_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_blueprints (
  chapter_blueprint_id TEXT PRIMARY KEY,
  blueprint_id TEXT NOT NULL,
  chapter_key TEXT NOT NULL,
  title TEXT NOT NULL,
  objective TEXT,
  core_message TEXT,
  questions_json TEXT NOT NULL DEFAULT '[]',
  subsections_json TEXT NOT NULL DEFAULT '[]',
  evidence_theme_ids_json TEXT NOT NULL DEFAULT '[]',
  target_words INTEGER DEFAULT 0,
  planned_visual_types_json TEXT NOT NULL DEFAULT '[]',
  order_index INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (blueprint_id) REFERENCES report_blueprints(blueprint_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
  chapter_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  chapter_key TEXT NOT NULL,
  title TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapter_versions (
  chapter_version_id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  body_markdown TEXT NOT NULL,
  summary TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(chapter_id, revision),
  FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paragraphs (
  paragraph_id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  subsection_key TEXT,
  paragraph_type TEXT,
  text TEXT NOT NULL,
  order_index INTEGER NOT NULL DEFAULT 0,
  edit_state TEXT NOT NULL DEFAULT 'AI_EDITABLE',
  FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paragraph_evidence_links (
  paragraph_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (paragraph_id, evidence_id),
  FOREIGN KEY (paragraph_id) REFERENCES paragraphs(paragraph_id) ON DELETE CASCADE
);
