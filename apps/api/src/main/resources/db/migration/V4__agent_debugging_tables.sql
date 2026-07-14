-- Phase 1 core: agent runs, step graphs, verdicts, diagnoses (§9).
-- Cost columns on agent_steps are first-class, not JSONB — the Phase 2/3
-- cost-per-quality expansion queries them directly.

CREATE TABLE agent_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL,
  project_id      UUID NOT NULL REFERENCES projects(id),
  agent_id        TEXT NOT NULL,            -- customer-assigned agent name
  agent_version   TEXT,                     -- git sha / prompt version
  status          TEXT NOT NULL,            -- 'running' | 'succeeded' | 'failed'
  failure_source  TEXT,                     -- 'explicit' | 'exception' | 'output_check'
  step_count      INTEGER NOT NULL DEFAULT 0,
  total_cost_usd  NUMERIC(10,6) NOT NULL DEFAULT 0,  -- sum of step costs
  metadata        JSONB DEFAULT '{}',
  started_at      TIMESTAMPTZ NOT NULL,
  ended_at        TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_steps (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL,
  seq             INTEGER NOT NULL,         -- topological order within run
  parent_step_ids UUID[] DEFAULT '{}',      -- input-producing ancestors
  step_type       TEXT NOT NULL,            -- 'llm' | 'tool' | 'retrieval' | 'handoff'
  name            TEXT NOT NULL,
  model           TEXT,                     -- for llm steps
  input_tokens    INTEGER,
  output_tokens   INTEGER,
  cost_usd        NUMERIC(10,6),            -- computed at ingest from tokens x model price
  latency_ms      INTEGER,
  storage_key     TEXT,                     -- full input/output payload in MinIO
  embedding       vector(1536),             -- failure-signature embedding (Phase 2 clustering)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE step_verdicts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_id         UUID NOT NULL REFERENCES agent_steps(id) ON DELETE CASCADE,
  run_id          UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL,
  contract_id     UUID REFERENCES rubrics(id),  -- rubrics repurposed as step contracts
  passed          BOOLEAN NOT NULL,
  score           FLOAT NOT NULL,           -- 0.0-1.0, below contract threshold = faulted
  failure_class   TEXT,                     -- 'retrieval_miss' | 'hallucinated_content' | ...
  judge_reasoning TEXT,
  judge_model     TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE diagnoses (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            UUID NOT NULL UNIQUE REFERENCES agent_runs(id) ON DELETE CASCADE,
  org_id            UUID NOT NULL,
  origin_step_id    UUID REFERENCES agent_steps(id),
  propagated_step_ids UUID[] DEFAULT '{}',
  failure_class     TEXT NOT NULL,
  evidence          TEXT,                   -- quoted spans supporting the verdict
  explanation       TEXT,                   -- one-paragraph causal narrative
  method            TEXT NOT NULL,          -- 'deterministic' | 'escalated'
  escalation_model  TEXT,                   -- set when method = 'escalated'
  wasted_cost_usd   NUMERIC(10,6),          -- cost of origin step + all downstream steps
  confirmed_by_user BOOLEAN,                -- fix-rate feedback: did the fix land here?
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
