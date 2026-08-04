PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reviews (
  review_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  chapter_id TEXT,
  scope TEXT NOT NULL,
  reviewer_type TEXT NOT NULL,
  decision TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_issues (
  issue_id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL,
  chapter_id TEXT,
  paragraph_id TEXT,
  severity TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  description TEXT NOT NULL,
  recommendation TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN',
  FOREIGN KEY (review_id) REFERENCES reviews(review_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quality_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL,
  chapter_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  unsupported_claim_count INTEGER NOT NULL DEFAULT 0,
  citation_mismatch_count INTEGER NOT NULL DEFAULT 0,
  numeric_mismatch_count INTEGER NOT NULL DEFAULT 0,
  open_critical_count INTEGER NOT NULL DEFAULT 0,
  open_major_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_edition ON reviews(edition_id, scope);
