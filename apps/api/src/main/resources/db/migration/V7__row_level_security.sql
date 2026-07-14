-- Row-Level Security (§9). HAND-CODED — a missed org_id filter in one query
-- leaks customer data.
--
-- FORCE is required: the app connects as the table owner (single-role compose
-- setup), and owners bypass plain RLS. With FORCE + a policy that reads
-- current_setting WITHOUT missing_ok, any query on a tenant table with no org
-- context on the connection fails loudly (fail-closed) instead of leaking.
--
-- The API sets app.current_org_id per request via TenantAwareDataSource
-- (session-scoped set_config + RESET on connection release). Workers set it
-- per job with transaction-scoped set_config(..., true).

ALTER TABLE projects       ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects       FORCE  ROW LEVEL SECURITY;
ALTER TABLE test_suites    ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_suites    FORCE  ROW LEVEL SECURITY;
ALTER TABLE traces         ENABLE ROW LEVEL SECURITY;
ALTER TABLE traces         FORCE  ROW LEVEL SECURITY;
ALTER TABLE slate_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE slate_runs     FORCE  ROW LEVEL SECURITY;
ALTER TABLE slate_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE slate_jobs     FORCE  ROW LEVEL SECURITY;
ALTER TABLE rubrics        ENABLE ROW LEVEL SECURITY;
ALTER TABLE rubrics        FORCE  ROW LEVEL SECURITY;
ALTER TABLE agent_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs     FORCE  ROW LEVEL SECURITY;
ALTER TABLE agent_steps    ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_steps    FORCE  ROW LEVEL SECURITY;
ALTER TABLE step_verdicts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_verdicts  FORCE  ROW LEVEL SECURITY;
ALTER TABLE diagnoses      ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnoses      FORCE  ROW LEVEL SECURITY;
ALTER TABLE baselines      ENABLE ROW LEVEL SECURITY;
ALTER TABLE baselines      FORCE  ROW LEVEL SECURITY;

-- With no explicit WITH CHECK, the USING expression also guards INSERT/UPDATE.
CREATE POLICY org_isolation ON projects
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON test_suites
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON traces
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON slate_runs
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON slate_jobs
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON rubrics
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON agent_runs
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON agent_steps
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON step_verdicts
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON diagnoses
  USING (org_id = current_setting('app.current_org_id')::uuid);
CREATE POLICY org_isolation ON baselines
  USING (org_id = current_setting('app.current_org_id')::uuid);
