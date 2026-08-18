-- Phase 1: Job event projection whitelist (no raw prompts/responses)

CREATE TABLE IF NOT EXISTS job_events (
    job_event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    sequence_no INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    workflow_name TEXT,
    agent_name TEXT,
    invocation_id TEXT,
    session_id TEXT,
    progress REAL,
    sanitized_error_code TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_seq
ON job_events(job_id, sequence_no);
