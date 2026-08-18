-- Phase 1: Persistent jobs for ADK analyze vertical slice

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error_message TEXT,
    adk_app_name TEXT NOT NULL,
    adk_user_id TEXT NOT NULL,
    adk_session_id TEXT NOT NULL,
    adk_invocation_id TEXT,
    current_workflow TEXT,
    current_agent TEXT,
    current_chapter TEXT,
    last_event_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_project_created
ON jobs(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
ON jobs(status, created_at ASC);

-- DB-level concurrency guard for analyze jobs.
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_analyze
ON jobs(project_id, job_type)
WHERE status IN ('queued', 'running');
