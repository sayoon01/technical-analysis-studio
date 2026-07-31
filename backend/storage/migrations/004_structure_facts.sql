-- Diagram / process structure facts (nodes, edges, groups)
CREATE TABLE IF NOT EXISTS structure_facts (
    fact_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    fact_kind TEXT NOT NULL,  -- PROCESS | ARCHITECTURE
    title TEXT,
    payload_json TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    verification_status TEXT DEFAULT 'REQUIRES_VISUAL_CHECK',
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_structure_facts_source
    ON structure_facts(source_id, page_number);
