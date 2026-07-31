-- MVP schema (SQLite). Vector index is external; FTS5 for keyword search.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    stage TEXT NOT NULL DEFAULT 'CREATED',
    current_edition_id TEXT,
    resume_target_stage TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    filename TEXT NOT NULL,
    mime_type TEXT,
    role TEXT NOT NULL DEFAULT 'EVIDENCE_SOURCE',
    status TEXT NOT NULL DEFAULT 'UPLOADED',
    page_count INTEGER,
    storage_path TEXT,
    ocr_quality REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_pages (
    page_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    page_number INTEGER NOT NULL,
    page_type TEXT NOT NULL DEFAULT 'TEXT',
    text_layer_available INTEGER NOT NULL DEFAULT 1,
    image_path TEXT,
    width REAL,
    height REAL,
    UNIQUE(source_id, page_number)
);

CREATE TABLE IF NOT EXISTS content_blocks (
    block_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    page_number INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text TEXT NOT NULL,
    bbox_x0 REAL, bbox_y0 REAL, bbox_x1 REAL, bbox_y1 REAL,
    reading_order INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    parent_section TEXT
);

-- Standalone FTS (dual-write from ContentBlockRepository). No content= sync.
CREATE VIRTUAL TABLE IF NOT EXISTS content_blocks_fts USING fts5(
    block_id UNINDEXED,
    source_id UNINDEXED,
    page_number UNINDEXED,
    text
);

CREATE TABLE IF NOT EXISTS visual_assets (
    asset_id TEXT PRIMARY KEY,
    source_id TEXT,
    edition_id TEXT,
    visual_type TEXT NOT NULL,
    title TEXT,
    storage_path TEXT,
    render_spec_json TEXT,
    evidence_ids_json TEXT
);

CREATE TABLE IF NOT EXISTS metric_facts (
    metric_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    definition TEXT,
    measurement_method TEXT,
    baseline_value REAL,
    result_value REAL,
    change_value REAL,
    change_unit TEXT,
    direction TEXT,
    confidence REAL,
    verification_status TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS corpus_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    snapshot_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, snapshot_number)
);

CREATE TABLE IF NOT EXISTS corpus_snapshot_sources (
    snapshot_id TEXT NOT NULL REFERENCES corpus_snapshots(snapshot_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    PRIMARY KEY (snapshot_id, source_id)
);

CREATE TABLE IF NOT EXISTS report_plans (
    plan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    snapshot_id TEXT,
    title TEXT NOT NULL,
    subtitle TEXT,
    purpose TEXT,
    target_reader TEXT,
    report_summary TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outlines (
    outline_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES report_plans(plan_id),
    version INTEGER NOT NULL DEFAULT 1,
    approved INTEGER NOT NULL DEFAULT 0,
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS outline_nodes (
    node_id TEXT PRIMARY KEY,
    outline_id TEXT NOT NULL REFERENCES outlines(outline_id),
    parent_id TEXT,
    level INTEGER NOT NULL,
    "order" INTEGER NOT NULL,
    title TEXT NOT NULL,
    objective TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS report_editions (
    edition_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    edition_number INTEGER NOT NULL,
    parent_edition_id TEXT,
    corpus_snapshot_id TEXT NOT NULL,
    report_plan_id TEXT NOT NULL,
    outline_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TEXT NOT NULL,
    UNIQUE(project_id, edition_number)
);

CREATE TABLE IF NOT EXISTS sections (
    section_id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL REFERENCES report_editions(edition_id),
    outline_node_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT,
    content_markdown TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    revision_count INTEGER NOT NULL DEFAULT 0,
    evidence_pack_id TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS section_versions (
    version_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL REFERENCES sections(section_id),
    revision INTEGER NOT NULL,
    content_markdown TEXT NOT NULL,
    change_summary TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    block_ids_json TEXT,
    confidence REAL,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL,
    section_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    claim_type TEXT,
    importance TEXT,
    verification_status TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS claim_evidence_links (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_items(evidence_id),
    relation TEXT,
    PRIMARY KEY (claim_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL,
    reviewer_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_issues (
    issue_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(review_id),
    section_id TEXT NOT NULL,
    reviewer_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    issue_type TEXT,
    paragraph_id TEXT,
    description TEXT,
    recommendation TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS production_runs (
    run_id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS production_tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES production_runs(run_id),
    section_id TEXT,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    edition_id TEXT,
    artifact_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exports (
    export_id TEXT PRIMARY KEY,
    edition_id TEXT NOT NULL REFERENCES report_editions(edition_id),
    format TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
