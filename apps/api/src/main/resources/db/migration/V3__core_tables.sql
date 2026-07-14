-- Core + eval-era tables (§9). The eval-era tables (test_suites, slate_runs,
-- slate_jobs, baselines) are retained for the Phase 3 failure-replay regression
-- gate; rubrics are repurposed as step contracts (§10).

CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(org_id, slug)
);

-- API keys are org-scoped with an optional project claim (enforces project
-- isolation without a DB lookup per request — §12).
CREATE TABLE api_keys (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id   UUID REFERENCES projects(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  key_prefix   TEXT NOT NULL,               -- first 8 chars, for display in the dashboard
  key_hash     TEXT NOT NULL UNIQUE,        -- SHA-256(key || server pepper), hex
  last_used_at TIMESTAMPTZ,
  revoked_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE test_suites (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  org_id      UUID NOT NULL,  -- denormalized for RLS
  name        TEXT NOT NULL,
  description TEXT,
  sample_count INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Traces (single LLM call records — degenerate one-step case)
CREATE TABLE traces (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL,
  project_id      UUID NOT NULL REFERENCES projects(id),
  prompt          TEXT NOT NULL,
  response        TEXT NOT NULL,
  model           TEXT NOT NULL,
  latency_ms      INTEGER,
  input_tokens    INTEGER,
  output_tokens   INTEGER,
  metadata        JSONB DEFAULT '{}',
  embedding       vector(1536),  -- text-embedding-3-small
  storage_key     TEXT,          -- pointer to full payload in MinIO
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rubrics — repurposed as step contracts (§10); built-ins seeded by the worker
CREATE TABLE rubrics (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL,
  project_id  UUID REFERENCES projects(id),
  name        TEXT NOT NULL,
  yaml_config TEXT NOT NULL,     -- raw YAML stored as text
  parsed_config JSONB NOT NULL,  -- parsed + validated at write time
  is_builtin  BOOLEAN DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE slate_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL,
  project_id      UUID NOT NULL REFERENCES projects(id),
  suite_id        UUID REFERENCES test_suites(id),
  name            TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  -- 'pending' | 'running' | 'complete' | 'failed'
  triggered_by    TEXT,  -- 'ci' | 'manual' | 'scheduled'
  git_ref         TEXT,
  baseline_run_id UUID REFERENCES slate_runs(id),
  total_jobs      INTEGER NOT NULL DEFAULT 0,
  completed_jobs  INTEGER NOT NULL DEFAULT 0,
  passed          BOOLEAN,
  mean_score      FLOAT,
  score_delta     FLOAT,  -- vs baseline
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);

CREATE TABLE slate_jobs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      UUID NOT NULL REFERENCES slate_runs(id) ON DELETE CASCADE,
  org_id      UUID NOT NULL,
  trace_id    UUID REFERENCES traces(id),
  rubric_id   UUID NOT NULL REFERENCES rubrics(id),
  status      TEXT NOT NULL DEFAULT 'pending',
  score       FLOAT,
  score_breakdown JSONB,  -- per-criterion scores
  judge_reasoning TEXT,
  judge_model TEXT,
  queue_job_id TEXT,      -- eval-era pointer, dormant until Phase 3
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  scored_at   TIMESTAMPTZ
);

CREATE TABLE baselines (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id),
  org_id      UUID NOT NULL,
  run_id      UUID NOT NULL REFERENCES slate_runs(id),
  name        TEXT NOT NULL DEFAULT 'default',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, name)
);
