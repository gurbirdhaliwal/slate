# slate-worker

The diagnosis engine (Layer 2, §10 of the product doc). Polls the Postgres
`analysis_jobs` queue (`FOR UPDATE SKIP LOCKED`) and processes two job kinds:

- **`step_verdict`** (Stage 1): judge one step against its typed contract via
  Claude Haiku; store a `step_verdicts` row; atomically decrement the run
  counter — the last verdict enqueues the localization job.
- **`localization`** (Stage 2): deterministic graph walk separating origin from
  propagated faults; ambiguous graphs escalate to one Claude Sonnet call;
  store the `diagnoses` row.

Hand-code territory (§13): the claim/retry SQL, the deterministic walk, the
escalation trigger, verdict parsing, and both judge prompts.

## Run locally

```bash
pip install -e ".[dev]"
DATABASE_URL=postgresql://slate:slate@localhost:5432/slate \
ANTHROPIC_API_KEY=sk-ant-... slate-worker
```

Scale in production via compose replicas — SKIP LOCKED makes claims safe at
any worker count.
