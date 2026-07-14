-- The job queue is just a table (§10). Enqueue happens in the same transaction
-- as the ingest write. NOT under RLS: workers claim jobs across all orgs, then
-- set transaction-scoped org context per job before touching tenant tables.

CREATE TABLE analysis_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       UUID NOT NULL,
  run_id       UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  step_id      UUID REFERENCES agent_steps(id),   -- NULL for localization jobs
  kind         TEXT NOT NULL,      -- 'step_verdict' | 'localization'
  status       TEXT NOT NULL DEFAULT 'queued',
  -- 'queued' | 'running' | 'done' | 'dead'
  attempts     INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after    TIMESTAMPTZ NOT NULL DEFAULT now(),  -- backoff scheduling
  locked_at    TIMESTAMPTZ,
  last_error   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_jobs_claimable ON analysis_jobs (run_after, created_at)
  WHERE status = 'queued';
-- Dead jobs stay in the table — inspect them, never auto-delete

-- Atomic run counter: when the last verdict lands, the worker enqueues the
-- localization job. MUST be updated via atomic UPDATE ... RETURNING (§10).
CREATE TABLE run_analysis_progress (
  run_id            UUID PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
  org_id            UUID NOT NULL,
  total_verdicts    INTEGER NOT NULL,
  pending_verdicts  INTEGER NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotency keys (§12) — Postgres instead of Redis; INSERT ... ON CONFLICT
-- makes check-and-claim atomic. A nightly cron deletes rows older than 24h.
CREATE TABLE idempotency_keys (
  org_id      UUID NOT NULL,
  key         TEXT NOT NULL,
  response    JSONB,                -- stored result, NULL while first request in flight
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, key)
);
