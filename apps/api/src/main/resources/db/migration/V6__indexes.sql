-- Common query patterns (§9)
CREATE INDEX idx_traces_org_project ON traces(org_id, project_id, created_at DESC);
CREATE INDEX idx_slate_jobs_run ON slate_jobs(run_id, status);
CREATE INDEX idx_slate_runs_project ON slate_runs(project_id, created_at DESC);
CREATE INDEX idx_traces_embedding ON traces USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Agent debugging query patterns
CREATE INDEX idx_agent_runs_project ON agent_runs(project_id, status, created_at DESC);
CREATE INDEX idx_agent_steps_run ON agent_steps(run_id, seq);
CREATE INDEX idx_step_verdicts_run ON step_verdicts(run_id, passed);
CREATE INDEX idx_diagnoses_class ON diagnoses(org_id, failure_class, created_at DESC);
CREATE INDEX idx_agent_steps_embedding ON agent_steps USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);  -- failure clustering (Phase 2)

-- Auth lookup: the ingest hot path resolves org from the hashed key
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash) WHERE revoked_at IS NULL;
