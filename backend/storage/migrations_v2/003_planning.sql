PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS report_strategies (
  strategy_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  corpus_snapshot_id TEXT,
  recommended_title TEXT NOT NULL,
  subtitle TEXT,
  target_reader TEXT,
  purpose TEXT,
  central_thesis TEXT,
  narrative_arc_json TEXT NOT NULL DEFAULT '[]',
  included_scope_json TEXT NOT NULL DEFAULT '[]',
  excluded_scope_json TEXT NOT NULL DEFAULT '[]',
  evidence_limitations_json TEXT NOT NULL DEFAULT '[]',
  recommended_pages INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS title_candidates (
  candidate_id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  title TEXT NOT NULL,
  style TEXT NOT NULL,
  rationale TEXT,
  rank_index INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (strategy_id) REFERENCES report_strategies(strategy_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outlines (
  outline_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  strategy_id TEXT,
  title TEXT NOT NULL,
  subtitle TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
  FOREIGN KEY (strategy_id) REFERENCES report_strategies(strategy_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS outline_nodes (
  node_id TEXT PRIMARY KEY,
  outline_id TEXT NOT NULL,
  parent_id TEXT,
  level INTEGER NOT NULL,
  order_index INTEGER NOT NULL,
  title TEXT NOT NULL,
  objective TEXT,
  core_message TEXT,
  evidence_theme_ids_json TEXT NOT NULL DEFAULT '[]',
  expected_length INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (outline_id) REFERENCES outlines(outline_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outlines_project ON outlines(project_id);
CREATE INDEX IF NOT EXISTS idx_outline_nodes_outline ON outline_nodes(outline_id, level, order_index);
