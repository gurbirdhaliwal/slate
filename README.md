# Slate — The Step-Level Debugger for AI Agents

When a multi-step agent fails in production, Slate pinpoints the **origin
step**, classifies **why** it failed, and reports **what the failure cost**.
The single source of truth for product and architecture decisions is
[slate-product-doc.md](slate-product-doc.md) — read §3 (wedge), §5
(architecture), and §13 (build vs vibecode rules) before touching anything.

## Repository layout

```
apps/
├── api/          Layer 1 — Spring Boot (Java 21) ingest + REST API
│                 Flyway migrations (hand-written SQL), Spring Security
│                 (API keys + JWT), tenant-aware DataSource for RLS
├── worker/       Layer 2 — Python diagnosis engine
│                 Postgres queue (SKIP LOCKED), Haiku step verdicts,
│                 deterministic fault localization + Sonnet escalation
└── dashboard/    Layer 4 — React 19 SPA (Vite, Tailwind, TanStack Query)
packages/
└── sdk-py/       Open-source Python SDK — step-graph capture (zero deps)
infra/
├── nginx/        Reverse proxy conf (serves SPA, proxies /v1/* to api)
└── observability/  Prometheus + Promtail configs
docker-compose.yml  Whole environment: nginx, api, worker, postgres
                    (timescaledb-ha: TimescaleDB + pgvector), minio;
                    --profile observability adds Grafana/Loki/GlitchTip
.github/workflows/   ci.yml (PR checks) · deploy-dev.yml (main -> dev)
                     · deploy-prod.yml (release tag -> prod, human-gated)
docs/github-setup.md One-time repo config: rulesets, environments, secrets
```

## Branching & deploys (local → dev → prod)

Trunk-based: feature branches merge to `main` via PR (CI required, direct
pushes blocked by ruleset). Merging auto-deploys the **dev** stack. Prod only
deploys from a published release tag (`v*`) and pauses for approval on the
`production` GitHub Environment — see [docs/github-setup.md](docs/github-setup.md).

## Quickstart (local dev)

```bash
cp .env.example .env          # fill in ANTHROPIC_API_KEY at minimum
make infra                    # Postgres (+pgvector/Timescale) + MinIO in Docker
make api                      # Spring Boot on :8080 — Flyway migrates on boot
make worker                   # diagnosis workers (needs DATABASE_URL/ANTHROPIC_API_KEY env)
make dashboard                # Vite dev server on :3000, proxies /v1 -> :8080
```

Or the full containerized stack: `make up` (nginx serves everything on :80).

## Verifying a change

- API: `cd apps/api && mvn test`
- Worker: `make test-worker` (queue semantics + localization walk + verdict parsing)
- Dashboard: `cd apps/dashboard && npm run build` (tsc + vite)

## The rules that matter (§13)

Hand-code (bugs are silent, customers trust the output): queue claim/retry SQL,
verdict parsing, the localization walk, judge prompts, auth filter chain +
key hashing, TenantContext/TenantAwareDataSource, RLS policies, migrations,
SDK public surface, idempotency. **Vibecode freely:** dashboard pages, charts,
Dockerfiles, controller boilerplate, S3 utilities.

Two deliberate deviations from the doc's SQL, flagged in the migrations:
- `V7` adds `FORCE ROW LEVEL SECURITY` (the app connects as table owner, which
  would otherwise bypass RLS entirely).
- `V8` leaves TimescaleDB hypertable conversion commented out — the doc's PKs
  and inbound FKs are incompatible with `create_hypertable`; converting is a
  conscious schema change for when volume demands it.

## Current state (base boilerplate)

Working end-to-end skeleton: SDK capture -> `POST /v1/ingest/runs` (validated,
cost computed, payloads to MinIO, verdict jobs enqueued transactionally) ->
worker verdicts -> localization -> `GET /v1/runs/{id}/diagnosis` -> dashboard.

Still stubbed (tracked TODOs): dashboard auth endpoints (`/auth/*` return 501),
API key issuance, JWT filter for dashboard routes, LangGraph auto-instrumentation,
OTel bridge, Slack/webhook alerts, rate limiting, backups cron, Uptime Kuma VPS.
