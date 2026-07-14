# Slate — The Step-Level Debugger for AI Agents
### Solo Founder Product Reference Document

> **Purpose:** This document is the single source of truth for building this product. It covers the why, what, how, and in what order. Reference it before every sprint. Update it as decisions change.

> **⚠ Repositioned 2026-07-13:** Slate is no longer an evaluation/observability platform. It is a **causal debugger for multi-step agent failures** — it pinpoints the exact step that broke, classifies why, and attaches the dollar cost of the failure. Per-step cost attribution is a first-class schema property from day one; the cost-per-quality story is the Phase 2/3 expansion. Rationale: the previous wedge (OSS SDK + proprietary LLM-as-judge CI regression gate) collided head-on with Confident AI (YC W25, 2-year head start, 16k+ star DeepEval, enterprise logos). See §3 for the new wedge and §18 for the decisions this breaks.

---

## Table of Contents

1. [The Idea & Why It Matters](#1-the-idea--why-it-matters)
2. [Market Opportunity](#2-market-opportunity)
3. [Product Strategy & Wedge](#3-product-strategy--wedge)
4. [Competitive Landscape](#4-competitive-landscape)
5. [Architecture Overview](#5-architecture-overview)
6. [Full Tech Stack](#6-full-tech-stack)
7. [Infrastructure & Hosting](#7-infrastructure--hosting)
8. [Cost Model](#8-cost-model)
9. [Database Design](#9-database-design)
10. [Slate Engine Design](#10-slate-engine-design)
11. [SDK Design](#11-sdk-design)
12. [API Contract](#12-api-contract)
13. [Build vs Vibecode Guide](#13-build-vs-vibecode-guide)
14. [Phase-by-Phase Build Plan](#14-phase-by-phase-build-plan)
15. [Monetization](#15-monetization)
16. [Open Source Strategy](#16-open-source-strategy)
17. [Scaling Strategy](#17-scaling-strategy)
18. [Decision Log](#18-decision-log)

---

## 1. The Idea & Why It Matters

> **⚠ Changed for the agent-debugging pivot:** the core-problem framing and pain ranking below were rewritten to lead with agent failure diagnosis. The original framing led with prompt-regression testing (now Confident AI's owned territory; regression protection returns as Slate's Phase 3, derived from diagnosed failures).

### The Core Problem

Every team shipping a multi-step AI agent faces the same on-call crisis: the agent fails — a wrong answer, a botched action, an infinite loop — and nobody can tell **which step broke or why**. The evidence is a 15-step JSON log dump. The developer reads spans one by one, reconstructs the causal chain in their head, and burns an afternoon finding the one step where things went wrong.

Traditional software has debuggers. A stack trace points at the line that threw. **Agents have nothing equivalent.** Tracing tools (LangSmith, Arize Phoenix, Langfuse) show you *what happened* — every span, every token — but the causal work of finding *where and why it broke* is still done by a human reading logs. And because agent failures are usually semantic (a retrieval that missed, a hallucinated field, malformed tool arguments), infrastructure monitoring never fires: latency is fine, error rate is zero, and the run still failed.

Every one of those failures also has a price tag. A 30-step agent run that fails at step 4 still pays for steps 5–30. Nobody can say what a recurring failure class costs per week, because no tool links cost to failure at the step level.

### The Specific Pains (Ranked by Acuteness)

**1. Black-box agent failures**
When a multi-step agent fails, the developer gets a log dump — not a diagnosis of which decision in which step caused the failure. Debugging a 15-step agent chain by reading JSON logs is brutal, and it recurs every time the agent misbehaves.

**2. No cost attribution at the step level**
Token spend explodes. Nobody knows which agent loop, which step, or which failure mode is burning it. Finance asks engineering for the number. Engineering has no answer — and no tool connects dollars to failures.

**3. Silent quality drift in production**
A model provider updates their model. A new category of user inputs starts hitting the system. Failure rates creep up over days or weeks. No alert fires because latency is fine and error rates are zero. The team finds out from a customer complaint.

**4. No regression detection on agent changes**
When a developer edits a system prompt, swaps a model, or restructures a chain, there is no automated check that previously-diagnosed failures stay fixed. Teams rely on manual review of a handful of examples — which misses edge cases and doesn't scale.

**5. Diagnosis tooling is rebuilt per-project**
Every team that wants to understand agent failures builds ad-hoc scripts: log parsers, one-off judge prompts, spreadsheet triage. It takes weeks, produces no reusable data, and is rebuilt every time.

### Why This Is an Infrastructure Product (Not a Tool)

The distinction matters for pricing, positioning, and defensibility.

A *tool* is used manually, on-demand. A *platform* is integrated into workflows and becomes load-bearing. Slate is infrastructure: the SDK instruments the agent itself, every production run flows through it, and the accumulated corpus of diagnosed failures (origin step → failure class → confirmed fix) lives here. Once integrated, switching cost is high — ripping it out means losing both the instrumentation and the failure history that makes future diagnoses smarter. In Phase 3 it additionally becomes the CI gate that replays known failures on every deploy.

This is the same moat that makes Datadog, Stripe, and Segment hard to replace — not because competitors don't exist, but because the integration depth makes switching expensive.

---

## 2. Market Opportunity

### Market Size

| Metric | Value |
|--------|-------|
| AI observability market (2026) | ~$2.7B |
| Projected market (2030) | ~$9.3B |
| CAGR | ~36% |
| VC deployed into LLMOps (2024–2026) | ~$1.1B |
| Enterprises with AI in production (2026) | ~72% |

Gartner projects that by 2028, LLM observability tooling will be present in 50% of all GenAI deployments — up from ~15% in early 2026. The market is in the fast-growth phase of the S-curve.

### Why Now

Three macro tailwinds converged in 2025–2026:

1. **AI in production went mainstream.** Shipping AI is no longer a research exercise. Every product team has at least one AI feature in production. The operational problems that come with this (reliability, quality, cost) are now universal.

2. **Agent architectures exploded.** Single LLM call → structured output is table stakes. Production systems now chain multiple models, tools, and retriSlate steps. Observability for agents is meaningfully harder than for completions — and most tools haven't caught up.

3. **The horizontal tool layer is getting crowded.** Basic token logging and latency tracking are commoditizing. The differentiated opportunity is in evaluation quality, vertical-specific rubrics, agent tracing, and business-level cost attribution — none of which the incumbents have built well.

### Target Buyer

**Primary:** Full-stack developers and ML engineers at companies shipping AI-powered products (B2B SaaS, developer tools, AI-native startups). Team sizes 5–50 engineers.

**Secondary:** Platform/infra teams at larger companies (50–500 engineers) who need a managed Slate layer rather than building it internally.

**Not yet:** Large enterprise (complex procurement, long sales cycle — Phase 3+ territory).

---

## 3. Product Strategy & Wedge

### What Slate Is Not

Slate is **not an evaluation platform**. It does not start with test suites, rubrics-against-final-outputs, or a CI quality gate. That wedge is owned: Confident AI (YC W25) has a 2-year head start on the identical OSS-SDK-plus-proprietary-judge-engine architecture, 16k+ GitHub stars on DeepEval, and enterprise logos. Competing there head-on as a solo founder means fighting a better-resourced incumbent on their exact home turf.

Slate is a **debugger**. The category question it answers is different in kind: incumbents answer *"how good is my AI?"* (evaluation) or *"what did my agent do?"* (tracing). Slate answers *"which step broke, why, and what did it cost me?"* (diagnosis).

### The Wedge: Step-Level Causal Diagnosis of Agent Failures

**The wedge:** When a multi-step agent run fails in production, Slate automatically pinpoints the *origin step* — the earliest step that produced a faulty output from sound inputs — classifies the failure, shows the evidence, and reports what the failure cost in dollars. The developer opens a diagnosis, not a log dump.

The core mechanism has three stages:

1. **Step capture.** The SDK records the agent run as a structured step graph — every LLM call, tool call, retrieval, and handoff, with inputs, outputs, and per-step token cost. This is richer than a trace: steps carry typed roles (`retrieval`, `llm`, `tool`, `handoff`) and explicit input/output edges.

2. **Step verdicts.** Instead of judging the final output, the engine judges each step against its *local contract*: "given exactly what this step received, did it do its job?" A retrieval step is judged on whether the passages can answer the question; a drafting step on faithfulness to those passages; a tool step on argument validity. Each verdict carries a failure class (retrieval miss, hallucinated content, malformed tool call, ignored instruction, bad handoff, planning error…).

3. **Fault localization.** A causal pass walks the step graph and separates the *origin* fault (bad output from good inputs) from *propagated* damage (steps that failed because they were fed garbage). Deterministic graph logic handles the clear cases; ambiguous runs escalate to a stronger model that reasons over the full graph. The output is a diagnosis: origin step, failure class, evidence, explanation, cost.

**Cost is a first-class property of every step, not a bolt-on dashboard.** Every step row carries token counts and computed dollar cost; every diagnosis reports what the failed run cost and what that failure class costs cumulatively. This is deliberately built into the schema from day one so that the Phase 2/3 expansion — cost-per-quality analytics ("this model swap saved $X/month and cut the retrieval-miss rate by Y%") — is a query, not a rearchitecture.

### Why This Wedge

- **The pain is acute and unserved.** Tracing tools display; humans still diagnose. No shipping product owns "tells you which step broke and why."
- **It is orthogonal to Confident AI's moat.** Their unit of analysis is the test case and the final output. Fast-following Slate means rebuilding their engine around a different primitive — steps, contracts, and causal graphs — not adding a feature.
- **The engine largely survives the pivot.** The LLM-as-judge pipeline (queue, workers, judge calls, score storage) is repointed from final outputs to individual steps. The build risk is concentrated in one new component: the localization pass.
- **It compounds into a data moat.** Every confirmed diagnosis (origin step → failure class → the fix that worked, validated by fix-rate feedback from design partners) builds a labeled corpus no incumbent collects. Diagnosis quality improves with volume in a way dashboards don't.
- **It's narrow enough for one person to own.** "AI observability" is a category war. "Agent failure diagnosis" is a beachhead.

### Where the Old Wedge Went

Prompt/model regression testing is not discarded — it is *derived*. In Phase 3, Slate replays previously-diagnosed failure runs against new agent versions in CI: pass means known failures stay fixed and no new origin faults appear. This is a differentiated regression gate — built from real diagnosed production failures, not hand-curated test suites — and it arrives after the diagnosis corpus exists to power it.

### Expansion Path

```
Phase 1 (Wedge)
└── Step-graph capture (Python SDK + LangGraph auto-instrumentation)
    └── Step verdicts (LLM-as-judge per step, typed contracts)
    └── Fault localization (deterministic + escalation)
    └── Diagnosis view: origin step, failure class, evidence, cost

Phase 2 (Aggregation & cost layer)
└── Always-on production capture + success-run sampling
└── Failure clustering ("retrieval misses at step 3, 40% of failures")
└── Cost-per-failure analytics: $ burned per failure class / agent / week
└── Custom step contracts (YAML)

Phase 3 (Regression & cost-per-quality)
└── Failure-derived regression suites: replay diagnosed failures in CI
└── Cost-per-quality dashboards: $ vs failure rate per agent version / model
└── Framework coverage: CrewAI, OpenAI Agents SDK, Claude Agent SDK, raw OTel

Phase 4 (Enterprise)
└── Vertical failure taxonomies (legal, healthcare, finance)
└── SSO, RBAC, audit logs
└── On-prem / VPC deployment option
```

Each phase is a natural upsell to customers already instrumented. The Phase 1 moat is the instrumentation plus the accumulating diagnosis corpus; the Phase 3 CI gate adds the pipeline stickiness the old strategy wanted — earned from a defensible position instead of contested ground.

---

## 4. Competitive Landscape

The field splits into two camps, and Slate is deliberately in neither: **evaluation platforms** answer "how good is my AI?" and **tracing/observability tools** answer "what did my agent do?" Slate answers "which step broke, why, and what did it cost?" — no incumbent's core mechanism produces that output.

| Competitor | Strength | Gap You Exploit |
|------------|----------|-----------------|
| **Confident AI / DeepEval** (YC W25) | 16k+ star OSS eval framework, LLM-as-judge CI regression gate, production monitoring, enterprise logos (BCG, AstraZeneca, Microsoft), 2-year head start | Unit of analysis is the test case and the final output. Agent tracing is a viewer bolted onto an eval platform — no per-step verdicts, no fault localization, no cost-failure linkage. Their moat (eval suites wired into CI) is orthogonal to post-hoc diagnosis of production failures; matching Slate means rebuilding their engine around a different primitive, not shipping a feature. |
| **LangSmith** | Deepest agent tracing, massive distribution via LangChain/LangGraph | A trace *viewer* — the human still reads spans and does the causal work. Step-level evals exist but produce scores, not diagnoses. Perceived LangChain lock-in pushes non-LangChain teams away. |
| **Arize Phoenix** | Solid OSS agent tracing on OTel standards | Visualizes, doesn't diagnose. Academic/research-heavy, poor onboarding. |
| **Braintrust** | Polished eval UX, strong enterprise traction | Final-output evaluation platform; enterprise-priced; agents are a secondary surface. |
| **Langfuse** | Good open-source base, ClickHouse backend | Logging/observability lens — no step verdicts, no localization. Now owned by ClickHouse; roadmap gravity is analytics, not diagnosis. |
| **Galileo** | Strong hallucination detection | Expensive, complex setup, enterprise only. Detects *that* output is bad, not *which step* made it bad. |
| **Helicone** | Great DX, proxy-based, good cost tracking | Logging only — cost without quality, no step semantics, no diagnosis. |
| **Datadog LLM Observability** | Enterprise distribution, APM muscle | Infrastructure-health lens. Generic quality checks; no causal step analysis. Agents are spans, not step graphs. |

**Your differentiation:**
- **Unit of analysis is the step, not the test case or the trace** — verdicts and cost attach per step, diagnoses attach per run
- **Output is a diagnosis, not a dashboard** — origin step, failure class, evidence, cost; the developer's causal work is done by the engine
- **Cost and quality in the same object** — every diagnosis carries a dollar figure; no incumbent joins spend to failure at step granularity
- **Works on real production failures, post-hoc** — no test-suite curation required to get value on day one
- **Open-source SDK, OTel-compatible step capture** (trust + adoption; teams already emitting OTel GenAI spans onboard without re-instrumenting)
- **Compounding data moat**: confirmed diagnoses (origin → class → validated fix) form a labeled corpus that improves localization accuracy with volume

---

## 5. Architecture Overview

The system has four layers. Each layer is independently deployable and testable.

> **⚠ Restacked 2026-07-13:** self-hosted, full-control stack — Spring Boot ingest API, Python diagnosis workers, Postgres-backed job queue (no Redis), MinIO object storage, React SPA behind Nginx, Docker Compose on a VPS. No backend-as-a-service. See §6/§7 for the stack and §18 for the decision.

**What survives the product pivot unchanged:** the ingest → queue → judge-worker → Postgres/object-storage → dashboard skeleton. **What the pivot changed:** the SDK captures step graphs instead of single completions; the engine gains a second stage (fault localization) after step verdicts; storage gains agent-run/step tables; the surface is a diagnosis view instead of a score dashboard. The CI webhook path is deferred to Phase 3.

```
┌─────────────────────────────────────────────────────┐
│  Customer codebase                                  │
│  ┌──────────┐  ┌──────────┐                        │
│  │ Python   │  │ TS SDK   │  (open source,          │
│  │ SDK      │  │ (Phase 2)│   OTel-compatible)      │
│  └────┬─────┘  └────┬─────┘                        │
│       └──────┬───────┘                              │
└──────────────┼──────────────────────────────────────┘
               │ HTTPS (batched step graphs, async)
               ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Ingest API (Spring Boot / Java 21)        │
│  - Bean Validation (step graph shape, edge refs)    │
│  - Auth (Spring Security: hashed API keys, JWT)     │
│  - Store raw step payloads to MinIO                 │
│  - On run completion: enqueue analysis jobs         │
│    (Postgres queue table, SKIP LOCKED)              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Diagnosis Engine (Python Workers)         │
│  Stage 1 — Step verdicts (fan-out, per step):       │
│  - Load step contract for the step's type           │
│  - Call Claude Haiku (LLM-as-judge, cached prompt)  │
│  - Store verdict + failure class                    │
│  Stage 2 — Fault localization (one job per run):    │
│  - Deterministic graph walk: origin vs propagated   │
│  - Ambiguous cases escalate to Claude Sonnet        │
│  - Store diagnosis, emit alert webhook              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: Storage                                   │
│  ┌──────────────────┐  ┌────────────────────┐      │
│  │ Postgres         │  │ MinIO (S3 API)     │      │
│  │ + pgvector       │  │ (raw step payload  │      │
│  │ + Timescale      │  │  blobs)            │      │
│  │ (agent_runs,     │  └────────────────────┘      │
│  │  agent_steps w/  │                              │
│  │  cost columns,   │                              │
│  │  step_verdicts,  │                              │
│  │  diagnoses)      │                              │
│  └──────────────────┘                              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4: Surface                                   │
│  ┌────────────────────┐  ┌──────────────────────┐  │
│  │ React SPA (Vite,   │  │ REST API             │  │
│  │ served by Nginx):  │  │ /v1/runs/{id}/       │  │
│  │ run timeline +     │  │   diagnosis          │  │
│  │ diagnosis view     │  │ (Slack/webhook       │  │
│  │                    │  │  alerts)             │  │
│  └────────────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Data Flow for a Diagnosis

1. Customer's agent runs in production; the SDK captures each step (type, inputs, outputs, model, token counts) and streams batches to the ingest API
2. The run ends. It is marked failed by one of: an explicit `run.fail()` from the customer's code, an uncaught exception, or an optional final-output check
3. Ingest finalizes the step graph, computes per-step dollar cost from token counts, enqueues Stage 1: one verdict job per step (a 12-step run = 12 jobs)
4. Verdict workers judge each step against its typed contract via Haiku (rubric system prompt cached across the run), storing a verdict + failure class per step
5. When the last verdict lands (atomic counter, same pattern as before), Stage 2 enqueues: the localization job walks the graph — a step whose verdict failed while all its input-producing ancestors passed is the *origin*; downstream failures are marked *propagated*
6. If the walk is ambiguous (multiple candidate origins, or all steps pass yet the run failed), the job escalates to one Claude Sonnet call over the full graph, returning origin step, failure class, and evidence
7. The diagnosis is stored and an alert fires (Slack/webhook): *"Run #4812 failed at step 3 (retrieval_miss): retrieved passages don't cover the user's question. Wasted cost: $0.42."*
8. The developer opens the dashboard to the run timeline with the origin step highlighted, evidence quoted, and cost annotated

**Which runs get analyzed:** failed runs always; successful runs sampled (~5%, configurable) to maintain per-step baselines. This is the primary COGS control — see §8.

Total latency target: diagnosis available < 90 seconds after run completion (parallelized verdict fan-out + one localization pass).

**Deferred to Phase 3 (unchanged mechanics, new trigger):** the CI replay flow — GitHub Actions re-runs diagnosed failure cases against a new agent version and polls `/v1/runs/{run_id}/result` for pass/fail. The polling endpoint, webhook HMAC, and idempotency design in §12 are retained for this.

---

## 6. Full Tech Stack

> **⚠ Restacked 2026-07-13** for full backend control — no backend-as-a-service (Clerk, Railway, Vercel, BetterStack all dropped). Founder-fluent technologies only: Java/Spring Boot for the API, Python for the diagnosis workers, React for the dashboard. Every service runs in a container you own. Stripe (§15) is the sole retained third-party service — payments are not realistically self-buildable.

### Backend API (Spring Boot)

| Layer | Technology | Why |
|-------|-----------|-----|
| Runtime | Java 21 LTS | Virtual threads make blocking-style code cheap for an IO-heavy ingest API; founder fluency |
| Framework | Spring Boot 3.x (Spring MVC) | Mature, batteries-included, zero learning curve for you |
| Auth | Spring Security + own `users` / `org_memberships` / `api_keys` tables | Full control. JWT (RS256) sessions for the dashboard; hashed+peppered API keys for the SDK ingest path |
| Validation | Jakarta Bean Validation | Schema-first validation on all ingest DTOs |
| Data access | jOOQ | Type-safe SQL you own — matches the hand-written-migrations rule. No Hibernate magic |
| Migrations | Flyway | Versioned, hand-written SQL. Review every migration before it runs |
| Queue | Postgres queue table (`FOR UPDATE SKIP LOCKED`) | No Redis/broker to operate. Enqueue is transactional with ingest writes; retries, backoff, and DLQ are columns you control (§10) |
| Logging | Logback → JSON (logstash encoder) → Loki | Structured logs, self-hosted aggregation |

### Diagnosis Workers (Python)

| Component | Technology | Why |
|-----------|-----------|-----|
| Runtime | Python 3.12 | Anthropic SDK is first-class; same language as the customer SDK — shared idioms and test fixtures |
| Job consumption | psycopg polling the Postgres queue | Same SKIP LOCKED table the API enqueues to; workers scale as identical containers |
| LLM judge | Claude Haiku (Stage 1 verdicts), Claude Sonnet (Stage 2 escalation) | Two-tier judging decision — see §8, §10, §18 |
| Contract format | YAML (customer-defined, Phase 2) | Config not code — unchanged |
| Embedding model | text-embedding-3-small (OpenAI) | $0.02/M tokens — failure-signature clustering in Phase 2, unchanged |
| Score normalization | Custom (0.0 – 1.0 float) | Unchanged |

### Data Layer

| Component | Technology | Why |
|-----------|-----------|-----|
| Primary DB | PostgreSQL 16 (self-hosted container) | Relational + vector + time-series + job queue in one engine — unchanged, now on your box |
| Vector search | pgvector extension | Unchanged |
| Time-series | TimescaleDB extension | Unchanged |
| Object storage | MinIO (self-hosted, S3-compatible) | Raw step payload storage under your control. Client code is standard S3 SDK (AWS SDK v2 in Java, boto3 in Python) — swapping to S3/R2 later is a config change |

### Frontend (React SPA)

| Component | Technology | Why |
|-----------|-----------|-----|
| Framework | React 19 + Vite (SPA) | The dashboard is an authenticated app — no SEO or SSR need, so no Next.js/Vercel. Static build served by Nginx |
| Routing | React Router | Standard SPA routing |
| UI components | shadcn/ui + Tailwind CSS | Unchanged |
| Charts | Recharts | Unchanged |
| State | Zustand + TanStack Query | Zustand for UI state; TanStack Query for server state against the Spring API |

### Infrastructure & Observability (all self-hosted)

| Component | Technology | Why |
|-----------|-----------|-----|
| Hosting | Single VPS (Hetzner CPX31: 4 vCPU / 8 GB) + Docker Compose | Full root control, whole environment declared in git, ~$16/mo |
| Reverse proxy / TLS | Nginx + Let's Encrypt (certbot) | Serves the SPA build, proxies `/v1/*` to Spring, terminates TLS |
| Error tracking | GlitchTip (self-hosted, Sentry-SDK-compatible) | Sentry's client SDKs, your box, one small container |
| Metrics + logs | Prometheus + Grafana + Loki | One Grafana for API latency, worker throughput, queue depth, Sonnet escalation rate |
| Uptime monitoring | Uptime Kuma on a separate ~$4 nano-VPS | Uptime checks must originate outside the box being watched |
| Backups | Nightly `pg_dump` → offsite storage box; MinIO `mc mirror`; weekly restore test | You own durability now — see §7 |

---

## 7. Infrastructure & Hosting

> **⚠ Restacked 2026-07-13:** replaces the Railway + Vercel setup. Everything below runs on hardware you rent directly, declared in two files in git (`docker-compose.yml` + Nginx conf).

### VPS Setup (single host, Docker Compose)

```
slate-prod (Hetzner CPX31 — 4 vCPU / 8 GB / 160 GB NVMe, ~$16/mo)
├── nginx        (TLS termination, serves React build, proxies /v1/* → api)
├── api          (Spring Boot ingest + REST API)
├── worker       (Python diagnosis workers — scale via compose replicas)
├── postgres     (16 + pgvector + timescaledb; also hosts the job queue)
├── minio        (raw step payload storage)
├── glitchtip    (error tracking)
└── prometheus + grafana + loki   (metrics, dashboards, logs)

uptime-kuma on a separate nano-VPS (~$4/mo), watching https://api.slate.io/health
```

**Why one VPS + Compose over Kubernetes/AWS at this stage:**
- Full root control, zero platform abstractions — the requirement that drove this stack
- The entire environment is reproducible from git: compose file, Nginx conf, Flyway migrations
- Vertical scaling is cheap and instant (resize to 16 GB is a reboot); split workers to a second VPS when CPU contention appears
- Migrate to AWS when $50K MRR makes the ops investment worth it (§17)

**Deploys:** GitHub Actions builds three images (api, worker, spa-build) and pushes to GHCR → SSH step on the VPS runs `docker compose pull && docker compose up -d`. Rollback = redeploy the previous image tag. Postgres and MinIO live on named volumes and are never recreated by a deploy. Run Flyway on API startup with a boot-fails-loudly policy if a migration errors.

**Environment variables** — `.env` on the host (chmod 600, never committed), referenced by `docker-compose.yml`:

```bash
# Required
DATABASE_URL=postgresql://...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...                          # embeddings only
JWT_PRIVATE_KEY_PATH=/secrets/jwt-rs256.pem    # dashboard session signing
API_KEY_PEPPER=...                             # server-side pepper for hashed customer API keys
MINIO_ROOT_USER=...
MINIO_ROOT_PASSWORD=...
MINIO_BUCKET=slate-payloads

# Config
SPRING_PROFILES_ACTIVE=prod
LOG_LEVEL=info
WORKER_CONCURRENCY=10
MAX_ANALYSIS_JOBS_PER_RUN=500
ANTHROPIC_MAX_CALLS_PER_10S=50                 # worker-side token bucket
```

### Backups (you own durability now)

- Nightly `pg_dump -Fc` → encrypted upload to a Hetzner Storage Box (offsite). Retain 14 daily + 8 weekly
- **Weekly automated restore test into a scratch container.** An untested backup is not a backup — this is non-negotiable once design partners send real data
- MinIO: nightly `mc mirror` of the payload bucket to the same Storage Box
- VPS snapshot before every deploy that includes a migration

### MinIO Bucket Structure

```
slate-payloads/
├── {org_id}/
│   └── runs/
│       └── {run_id}/
│           └── {step_id}.json       # full step input/output payload
```

Access via standard S3 clients (AWS SDK v2 in Java, boto3 in Python) with the MinIO endpoint. Swapping to S3 or R2 later is a config change, not a code change.

---

## 8. Cost Model

### Pre-Revenue Monthly Infra Cost

> **⚠ Restacked 2026-07-13:** self-hosted stack — cheaper than the Railway/Vercel setup (~$35 vs ~$50), and the free-tier SaaS line items are gone entirely.

| Service | Cost |
|---------|------|
| Hetzner CPX31 VPS (api, workers, Postgres, MinIO, observability) | ~$16/mo |
| Nano-VPS for Uptime Kuma | ~$4/mo |
| Hetzner Storage Box (offsite backups: pg_dump + MinIO mirror) | ~$4/mo |
| Domain + misc | ~$10/mo |
| **Claude judge costs (Haiku + Sonnet)** | **Variable** |
| **Total (excl. judges)** | **~$35/mo** |

> **⚠ Changed for the agent-debugging pivot:** the unit of COGS is now the *diagnosed run* (N step verdicts + occasional localization escalation), not the single eval job. Infra costs above are unchanged. These numbers need validation against real design-partner step counts.

### Judge Cost per Diagnosed Run

Haiku pricing (as of 2026): $0.25/M input tokens, $1.25/M output tokens. Sonnet: $3/M input, $15/M output.

A typical diagnosed run (~12 steps):

- **Stage 1 — step verdicts (Haiku, one per step):** contract system prompt ~500 tokens (cached across the run) + step payload ~800 tokens in, ~200 tokens out → ~$0.000575/verdict uncached, ~$0.00037 with caching. 12 verdicts ≈ **$0.0045**
- **Stage 2 — localization:** deterministic graph walk (free) resolves ~70% of runs. The ~30% that are ambiguous escalate to one Sonnet call over the full graph: ~6,000 tokens in, ~800 out ≈ $0.030 → blended **$0.009/run**

**Blended COGS per diagnosed run: ~$0.014** (roughly $0.02 with headroom for longer runs).

| Monthly diagnosed runs | Judge COGS |
|------------------------|------------|
| 1K | ~$14 |
| 10K | ~$140 |
| 50K | ~$700 |
| 100K | ~$1,400 |

**Gross margin check at $499/mo tier (10K diagnosed runs included):**
Revenue: $499 | Judge COGS: ~$140–200 | Gross margin: ~70%

### COGS Controls

1. **Prompt caching** on step-contract system prompts — all steps of the same type in a run share a contract, so hit rate is high (~99% after the first step of each type).
2. **Analyze failures, sample successes.** Failed runs are always analyzed; successful runs are sampled at ~5% for baselines. Customers with high failure rates cost more — which is exactly when they get the most value.
3. **Escalation budget.** The Sonnet localization call only fires on ambiguous graphs. Track the escalation rate; if it drifts above ~40%, tighten the deterministic walk before raising prices.
4. **Step-count cap per plan tier** (e.g., 50 steps/run on Pro) so pathological loop-heavy agents don't blow COGS.

---

## 9. Database Design

> **Note:** Write every migration by hand as Flyway SQL files. Never vibecode schema changes. Review every migration before it runs in production.

### Core Tables

```sql
-- Organizations (auth is self-owned — see also users, org_memberships, api_keys
-- tables owned by the Spring Security layer; hand-write those in Phase 1)
CREATE TABLE organizations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'free', -- 'free' | 'pro' | 'enterprise'
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Projects (logical grouping of evals)
CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(org_id, slug)
);

-- Test suites (a named collection of input samples)
CREATE TABLE test_suites (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  org_id      UUID NOT NULL,  -- denormalized for RLS
  name        TEXT NOT NULL,
  description TEXT,
  sample_count INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Traces (individual LLM call records)
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
  storage_key     TEXT,          -- pointer to full payload in object storage (MinIO)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Slate runs (a CI/CD triggered batch eval)
CREATE TABLE slate_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL,
  project_id      UUID NOT NULL REFERENCES projects(id),
  suite_id        UUID REFERENCES test_suites(id),
  name            TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  -- 'pending' | 'running' | 'complete' | 'failed'
  triggered_by    TEXT,  -- 'ci' | 'manual' | 'scheduled'
  git_ref         TEXT,  -- branch/commit triggering this run
  baseline_run_id UUID REFERENCES slate_runs(id),
  total_jobs      INTEGER NOT NULL DEFAULT 0,
  completed_jobs  INTEGER NOT NULL DEFAULT 0,
  passed          BOOLEAN,
  mean_score      FLOAT,
  score_delta     FLOAT,  -- vs baseline
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);

-- Slate jobs (individual scored samples within a run)
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
  queue_job_id TEXT,      -- analysis_jobs id for debugging (eval-era table, dormant until Phase 3)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  scored_at   TIMESTAMPTZ
);

-- Rubrics (Slate criteria definitions)
CREATE TABLE rubrics (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL,
  project_id  UUID REFERENCES projects(id),
  name        TEXT NOT NULL,
  yaml_config TEXT NOT NULL,  -- raw YAML stored as text
  parsed_config JSONB NOT NULL,  -- parsed + validated at write time
  is_builtin  BOOLEAN DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Baselines (pinned run scores for comparison)
CREATE TABLE baselines (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id),
  org_id      UUID NOT NULL,
  run_id      UUID NOT NULL REFERENCES slate_runs(id),
  name        TEXT NOT NULL DEFAULT 'default',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, name)
);
```

### Agent Debugging Tables

> **⚠ Added for the agent-debugging pivot.** These are now the Phase 1 core; the tables above are retained — `traces` still backs single-call capture, and `test_suites` / `slate_runs` / `slate_jobs` / `baselines` / `rubrics` power the Phase 3 failure-replay regression gate (rubrics are repurposed as step contracts, see §10). Cost columns on `agent_steps` are deliberately first-class, not JSONB metadata — the cost-per-quality expansion queries them directly.

```sql
-- Agent runs (one end-to-end agent execution)
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

-- Agent steps (typed nodes in the run's step graph)
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
  cost_usd        NUMERIC(10,6),            -- computed at ingest from tokens × model price
  latency_ms      INTEGER,
  storage_key     TEXT,                     -- full input/output payload in MinIO
  embedding       vector(1536),             -- failure-signature embedding (clustering)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Step verdicts (Stage 1 judge output, one per analyzed step)
CREATE TABLE step_verdicts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_id         UUID NOT NULL REFERENCES agent_steps(id) ON DELETE CASCADE,
  run_id          UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL,
  contract_id     UUID REFERENCES rubrics(id),  -- rubrics repurposed as step contracts
  passed          BOOLEAN NOT NULL,
  score           FLOAT NOT NULL,           -- 0.0–1.0, below contract threshold = faulted
  failure_class   TEXT,                     -- 'retrieval_miss' | 'hallucinated_content' | ...
  judge_reasoning TEXT,
  judge_model     TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Diagnoses (Stage 2 output, one per analyzed failed run)
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
```

### TimescaleDB Hypertable

```sql
-- Convert append-heavy tables to hypertables for time-series dashboard queries
SELECT create_hypertable('slate_jobs', 'created_at');
SELECT create_hypertable('traces', 'created_at');
SELECT create_hypertable('agent_steps', 'created_at');   -- highest-volume table in the system
```

### Row-Level Security

> Hand-code this. A missed `org_id` filter in one query leaks customer data.

```sql
-- Enable RLS on all tenant tables
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_suites ENABLE ROW LEVEL SECURITY;
ALTER TABLE traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE slate_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE slate_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rubrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_verdicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;

-- Example policy (repeat for each table)
CREATE POLICY org_isolation ON traces
  USING (org_id = current_setting('app.current_org_id')::uuid);
```

After Spring Security authenticates the request (JWT session or hashed API key), a filter resolves the org and stashes it in a `ThreadLocal`; a wrapped `DataSource` sets `app.current_org_id` on every connection the request uses:

```java
// TenantContext.java + TenantAwareDataSource.java — HAND-CODE THIS
public final class TenantContext {
  private static final ThreadLocal<UUID> ORG = new ThreadLocal<>();
  public static void set(UUID orgId) { ORG.set(orgId); }
  public static UUID get() { return ORG.get(); }
  public static void clear() { ORG.remove(); }   // MUST run in a finally block per request
}

public class TenantAwareDataSource extends DelegatingDataSource {
  @Override
  public Connection getConnection() throws SQLException {
    Connection conn = super.getConnection();
    UUID orgId = TenantContext.get();
    if (orgId == null) {              // no request without an org may touch tenant tables
      conn.close();
      throw new IllegalStateException("No org context on this thread");
    }
    try (PreparedStatement ps =
           conn.prepareStatement("SELECT set_config('app.current_org_id', ?, false)")) {
      ps.setString(1, orgId.toString());
      ps.execute();
    }
    return conn;
  }
}
```

**Pool-reset warning (hand-verify this):** with `set_config(..., false)` the setting persists on the pooled connection after release. Either run every request in a transaction and use `set_config(..., true)` (transaction-scoped, auto-reset), or wrap `close()` to `RESET app.current_org_id` before the connection returns to the pool. A stale `org_id` on a pooled connection is a cross-tenant data leak — the exact failure RLS exists to prevent. The same applies to the Python workers: they set the org context per job with transaction-scoped `set_config(..., true)`.

### Key Indexes

```sql
-- Common query patterns
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
```

---

## 10. Diagnosis Engine Design

> **⚠ Restructured for the agent-debugging pivot** (and restacked 2026-07-13: Python workers on a Postgres queue — see below). The judge-worker skeleton (queue fan-out, Haiku calls, prompt caching, atomic run counters, dead-job handling) survives intact. What changed with the pivot: rubrics become *step contracts* keyed by step type, the pipeline gains a Stage 2 localization pass, and the output is a diagnosis instead of a run score.

> **This is your core IP. Hand-code the contract execution, verdict parsing, and especially the localization walk. Vibecoding here risks silent correctness bugs — a wrong origin step destroys the product's core promise.**

### Step Contract Schema (YAML)

Contracts are stored in the existing `rubrics` table (repurposed — see §9) and validated at write time. Phase 1 ships built-in contracts for the common step types; custom contracts arrive in Phase 2.

```yaml
# Example contract set: RAG support agent
name: rag-support-agent
version: 1
fault_threshold: 0.5   # verdict score below this marks the step faulted

contracts:
  - match: retrieval          # applies to steps with step_type=retrieval
    prompt: |
      Given the query this step received, do the retrieved passages contain
      the information needed to answer it?
      Score 1.0 if fully sufficient, 0.5 if partial, 0.0 if irrelevant or
      missing the key facts. Failure class if faulted: retrieval_miss.

  - match: llm                # any LLM step
    prompt: |
      Judge ONLY against the inputs this step received. Is the output
      faithful to those inputs and responsive to its instruction?
      Score 0.0 if it introduces facts not present in the inputs
      (failure class: hallucinated_content) or ignores its instruction
      (failure class: ignored_instruction).

  - match: tool:*             # any tool call
    prompt: |
      Are the tool arguments well-formed for this tool's schema and
      consistent with the intent of the preceding step?
      Failure classes: malformed_tool_call, tool_execution_error.
```

### Failure Taxonomy (v1 — hand-maintain this list)

`retrieval_miss` · `hallucinated_content` · `malformed_tool_call` · `tool_execution_error` · `ignored_instruction` · `bad_handoff` · `planning_error` · `context_overflow`

Every verdict and diagnosis maps to exactly one class. This taxonomy powers Phase 2 clustering and cost-per-failure analytics — resist letting the judge invent free-text classes.

### Pipeline

```
Run marked failed (or sampled success) → analysis enqueued
         │
         ▼
STAGE 1 — Step verdicts (fan-out: one analysis_jobs row per step)
  Load contract matching step_type (cached in worker memory)
  Load step payload from DB + MinIO
  Build judge prompt:
    - System: contract prompt (cached across the run)
    - User: { step inputs, step output }
  Call Haiku, parse verdict (score, failure_class, reasoning)
  Store step_verdict
  Decrement run counter (atomic)
         │
         ▼  (last verdict lands)
STAGE 2 — Fault localization (one job per run)
  Deterministic walk over the step graph in topological order:
    origin-faulted := verdict failed AND all parent steps passed
    propagated     := verdict failed AND ≥1 parent origin/propagated
  If exactly one origin → diagnosis (method: 'deterministic')
  If ambiguous (0 or 2+ origins, or run failed but all steps passed):
    → one Claude Sonnet call with the full graph + all verdicts
    → returns origin step id, failure class, evidence quotes (method: 'escalated')
  Compute wasted_cost_usd = cost of origin step + all downstream steps
  Store diagnosis, set run analysis complete
  Emit alert (Slack/webhook)
```

**Hand-code the deterministic walk and the escalation trigger.** The Sonnet escalation prompt is also hand-code territory: it must demand quoted evidence and forbid naming a step without it — an unsupported diagnosis is worse than none.

### Verdict Prompt Template

```python
# worker/verdict_prompt.py — HAND-CODE THIS
def build_verdict_prompt(contract: StepContract, step: StepPayload) -> tuple[str, str]:
    system = f"""You are a step-level agent debugger. Judge this single step in
isolation: evaluate the output ONLY against the inputs the step received.
Do not penalize the step for upstream mistakes visible in its inputs.

{contract.prompt}

Respond with ONLY a JSON object in this exact format:
{{"score": <float 0.0-1.0>, "failure_class": <string from the allowed list, or null if passing>, "reasoning": "<one sentence>"}}

Allowed failure classes: {", ".join(FAILURE_CLASSES)}.
Do not include any other text. Score must be between 0.0 and 1.0 inclusive."""

    user = f"""Step: {step.name} ({step.step_type})

Inputs this step received:
{step.inputs}

Output this step produced:
{step.output}"""
    return system, user


def parse_verdict_response(raw: str) -> Verdict:
    # Strip any markdown fences the model might add
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(cleaned)

    score = parsed.get("score")
    if not isinstance(score, (int, float)) or not 0.0 <= score <= 1.0:
        raise VerdictParseError(f"Invalid score: {score}")

    failure_class = parsed.get("failure_class")
    if failure_class is not None and failure_class not in FAILURE_CLASSES:
        raise VerdictParseError(f"Unknown failure class: {failure_class}")

    return Verdict(
        score=round(float(score), 3),
        failure_class=failure_class,
        reasoning=str(parsed.get("reasoning", "")),
    )
```

### Job Queue (Postgres, no broker)

> **⚠ Restacked 2026-07-13:** BullMQ/Redis replaced by a Postgres queue table. Enqueue happens in the same transaction as the ingest write (a run can never be half-enqueued), and retry semantics are columns you own. Hand-code the claim SQL and retry logic — wrong semantics here mean jobs silently lost or run twice.

```sql
-- Flyway migration — the queue is just a table
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
```

### Python Worker Loop

```python
# worker/main.py — HAND-CODE THE STRUCTURE, vibecode the boilerplate
CLAIM_SQL = """
UPDATE analysis_jobs SET status = 'running', attempts = attempts + 1, locked_at = now()
WHERE id = (
  SELECT id FROM analysis_jobs
  WHERE status = 'queued' AND run_after <= now()
  ORDER BY created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING *;
"""

def work_loop(pool: ConnectionPool, limiter: TokenBucket) -> None:
    while True:
        job = claim_one(pool)          # runs CLAIM_SQL in its own transaction
        if job is None:
            time.sleep(0.5)            # queue empty — cheap poll
            continue
        try:
            limiter.acquire()          # ANTHROPIC_MAX_CALLS_PER_10S token bucket
            if job.kind == "step_verdict":
                process_verdict(job)   # Haiku call → store step_verdict → decrement counter
            else:
                process_localization(job)  # graph walk → maybe Sonnet → store diagnosis
            mark_done(pool, job)
        except Exception as exc:
            if job.attempts >= job.max_attempts:
                mark_dead(pool, job, exc)          # stays in table for inspection
            else:
                backoff = 2 ** job.attempts        # 2s, 4s, 8s
                requeue(pool, job, exc, run_after=now() + timedelta(seconds=backoff))
```

Concurrency = `WORKER_CONCURRENCY` threads per container (verdict work is IO-bound on the Anthropic API); scale further with compose replicas — SKIP LOCKED makes claims safe across any number of workers. The run-completion counter (last verdict enqueues the localization job) must be an atomic SQL `UPDATE ... RETURNING`, not read-then-write.

---

## 11. SDK Design

> **⚠ Restructured for the agent-debugging pivot.** The public surface is now step-graph capture, not completion wrapping. **Python ships first** (agent frameworks — LangGraph, CrewAI, OpenAI Agents SDK — are Python-dominant); TypeScript follows in Phase 2. The `traceCompletion` wrapper is retained as the degenerate single-step case. The old `runEval`/`getRunResult` surface returns in Phase 3 for failure-replay CI.

> **Hand-code the public API surface (function signatures, types, config interface). Vibecode the implementations.**

### Design Principles

1. **Zero behavior change to the customer's agent.** Capture buffers in-process and flushes async in batches — it never blocks or fails the agent's own calls.
2. **Three integration tiers, cheapest first:** (a) auto-instrumentation for supported frameworks (3 lines), (b) manual step API for custom agents, (c) OTel bridge for teams already emitting GenAI spans.
3. **Cost capture is not optional.** Every step records token counts (auto-extracted from provider responses where possible); the server computes dollar cost at ingest. This feeds the cost-per-quality expansion.

### Python SDK (Phase 1)

```python
# packages/sdk-py/slate/__init__.py — public surface

class SlateConfig(TypedDict, total=False):
    api_key: str
    base_url: str            # default: https://api.slate.io
    project_id: str
    flush_interval_ms: int   # default: 5000
    batch_size: int          # default: 50
    enabled: bool            # default: True — set False in local dev
    sample_success_rate: float  # default: 0.05 — fraction of successful runs analyzed

# --- Tier (a): framework auto-instrumentation (LangGraph first) ---
def instrument_langgraph(graph, *, agent_id: str, agent_version: str | None = None): ...

# --- Tier (b): manual step API for custom agents ---
class AgentRun:
    def step(self, *, type: StepType, name: str,
             parents: list[Step] | None = None) -> Step: ...
    def fail(self, reason: str | None = None) -> None:   # marks run failed → triggers diagnosis
    def succeed(self, final_output: Any | None = None) -> None: ...

class Step:
    def set_input(self, data: Any) -> None: ...
    def set_output(self, data: Any) -> None: ...
    def end(self, *, model: str | None = None,
            input_tokens: int | None = None,
            output_tokens: int | None = None) -> None: ...

def start_agent_run(*, agent_id: str, agent_version: str | None = None,
                    metadata: dict | None = None) -> AgentRun: ...

# --- Tier (c): OTel bridge ---
def from_otel_spans(spans: Sequence[ReadableSpan]) -> AgentRun:
    """Map OTel GenAI semantic-convention spans onto a Slate step graph."""

# --- Degenerate single-call case (kept from the original design) ---
def trace_completion(fn: Callable[[], T], metadata: TraceMetadata | None = None) -> T: ...
```

### Usage Example (what the customer writes)

```python
import slate

slate.init(api_key=os.environ["SLATE_API_KEY"], project_id="proj_abc123")

# Tier (a): LangGraph — three lines, steps captured automatically
graph = build_my_agent_graph()
slate.instrument_langgraph(graph, agent_id="support-agent", agent_version=GIT_SHA)

# Tier (b): custom agent loop
run = slate.start_agent_run(agent_id="support-agent", agent_version=GIT_SHA)

retrieval = run.step(type="retrieval", name="fetch_docs")
retrieval.set_input(user_question)
passages = vector_store.search(user_question)
retrieval.set_output(passages)
retrieval.end()

draft = run.step(type="llm", name="draft_answer", parents=[retrieval])
draft.set_input({"question": user_question, "passages": passages})
resp = anthropic.messages.create(model="claude-haiku-4-5", messages=[...])
draft.set_output(resp.content)
draft.end(model="claude-haiku-4-5",
          input_tokens=resp.usage.input_tokens,
          output_tokens=resp.usage.output_tokens)

if answer_rejected:
    run.fail(reason="user thumbs-down")   # ← this triggers the diagnosis
else:
    run.succeed(final_output=resp.content)
```

### GitHub Actions Integration (deferred to Phase 3)

The `Slate/action@v1` failure-replay gate ships in Phase 3: it re-runs previously-diagnosed failure cases against the new agent version and fails the check if a known failure regresses or a new origin fault appears. The original action template (API key, project id, pass threshold, git ref) carries over with a `replay-set` input replacing `suite-id`.

---

## 12. API Contract

> **⚠ Needs a follow-up pass for the agent-debugging pivot (deliberately not rewritten yet):** Phase 1 requires `POST /v1/ingest/runs` (step graphs) and `GET /v1/runs/:run_id/diagnosis`; the existing `/v1/ingest/traces`, `/v1/runs` (create), and CI webhook endpoints move to Phase 3 (failure replay). Auth, idempotency, and HMAC design below all carry over unchanged.

> **Hand-code the response schemas and auth. Vibecode the route handlers.**

These endpoints are public contracts. Once customers integrate them into CI pipelines, changes are breaking changes.

### Authentication

All API requests require:
```
Authorization: Bearer <api_key>
```

API keys are org-scoped, stored hashed in Postgres. Include a `project_id` claim in the key encoding to enforce project isolation without a DB lookup on every request.

### Core Endpoints

```
POST /v1/ingest/traces
  Body: TracePayload[]
  Response: { accepted: number; run_id?: string }
  Auth: API key
  Rate limit: 1000/min per org

POST /v1/runs
  Body: { suite_id, rubric_id, baseline_run_id?, git_ref? }
  Response: { run_id, status: 'pending', estimated_duration_s }
  Auth: API key

GET /v1/runs/:run_id
  Response: RunResult (see SDK types above)
  Auth: API key
  Note: Poll this from CI until status == 'complete' | 'failed'

GET /v1/runs/:run_id/jobs
  Response: { jobs: EvalJob[] }  // per-sample scores
  Auth: API key
  Pagination: ?limit=50&cursor=...

POST /v1/webhooks/ci
  Called BY Slate TO customer's CI (outbound webhook)
  Body: { run_id, passed, mean_score, score_delta, regressions }
  Signature: X-Slate-Signature: HMAC-SHA256

GET /health
  Response: { status: 'ok', version: string }
  Auth: None (used by Uptime Kuma and the compose healthcheck)
```

### Idempotency

The CI webhook endpoint and run creation must be idempotent. Use a customer-provided `Idempotency-Key` header. With no Redis in the stack, keys live in a small Postgres table — an `INSERT ... ON CONFLICT` makes the check-and-claim atomic:

```sql
CREATE TABLE idempotency_keys (
  org_id      UUID NOT NULL,
  key         TEXT NOT NULL,
  response    JSONB,                -- stored result, NULL while first request in flight
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, key)
);
-- nightly cron deletes rows older than 24h
```

```java
// IdempotencyService.java — HAND-CODE THIS
// INSERT .. ON CONFLICT DO NOTHING; if the row already existed, return its stored
// response (or 409 if still in flight). Write the response back in the same
// transaction that creates the run — key claim and run creation must be atomic.
```

---

## 13. Build vs Vibecode Guide

The decision rule: **if a bug is invisible to the customer but trusted by them, hand-code it. If a bug surfaces immediately as a visible error, vibecode it.**

### Hand-Code (20% of the codebase, 80% of the risk)

| Component | Why Manual |
|-----------|-----------|
| Slate scoring pipeline | Silent correctness bugs. Customer trusts the score. |
| Rubric YAML validation | Bad validation means malformed rubrics silently produce wrong scores |
| Judge prompt template | Small changes to wording produce large changes in score distribution |
| Score normalization | Off-by-one or float precision errors corrupt all downstream comparisons |
| Pass/fail threshold logic | A bug here gives a false green checkmark — the product's core promise |
| Queue claim/retry SQL (SKIP LOCKED, backoff, dead-jobs) | Wrong semantics = jobs silently lost or run twice |
| Spring Security filter chain + API key hashing | The auth Clerk used to own is now yours. A misconfigured matcher exposes tenant data |
| TenantContext + TenantAwareDataSource (incl. pool reset) | One missed org filter or one stale pooled connection = data leak between customers. Fatal for B2B |
| Database migrations | Irreversible. Review every migration SQL before running |
| RLS policies | See above |
| SDK public API surface | Public contract. Breaking changes churn early adopters |
| CI webhook HMAC signing | Security boundary. Vibecoded HMAC is usually wrong |
| Idempotency logic | Duplicate runs or double-billing. Hard to debug in production |

### Vibecode Freely

| Component | Notes |
|-----------|-------|
| Dashboard UI (React SPA pages) | Bugs are immediately visible. Iterate fast. |
| Chart components | Wrong chart renders wrong — you see it |
| Dockerfiles / docker-compose / Nginx conf | Fails loudly if wrong |
| Stripe checkout flow | Vibecode the UI. Hand-verify webhook signature + idempotency key |
| Email/Slack notification templates | Annoying if wrong, not catastrophic |
| YAML contract parser (outer layer) | Hand-write the schema validation. Vibecode the parsing utility |
| Worker process scaffolding (config, logging, pool setup) | Boilerplate around the hand-coded loop |
| jOOQ codegen config + repetitive DTOs | Write the schema SQL by hand. Vibecode the mapping boilerplate |
| REST controller boilerplate | Spring controller registration, request parsing |
| MinIO/S3 upload/download utilities | Standard S3 SDK calls |
| Admin dashboard | Internal tooling, not customer-facing |

### Vibecoding Workflow

When vibecoding, follow this loop:

1. **Write the type signature or interface first yourself.** Give the AI the shape.
2. **Prompt with constraints:** "Implement this function. It must: (a) handle X edge case, (b) throw typed errors on Y, (c) never mutate the input."
3. **Read every line of the output.** Don't generate-and-ship.
4. **Write one test for the edge case most likely to break.** Run it.
5. **Commit only after the test passes.**

For UI components, the loop is tighter — generate, look at it, adjust, done.

### Recommended AI Tools

- **Claude Code** — best for planning, complex refactors, explaining existing code, debugging. Use for the hand-code sections where you need to think carefully.
- **Cursor / Copilot** — best for filling in implementations against interfaces you've already defined. Use for vibecoding boilerplate.

---

## 14. Phase-by-Phase Build Plan

### Phase 1 — MVP (Weeks 1–12)

**Goal:** 3 design partners getting real diagnoses on production agent failures, and confirming them. Charge nothing.

Four extra weeks vs the original 8-week plan: ~2 for the localization pass (genuinely new engineering) and ~2 for self-hosted auth/org/API-key management plus VPS ops that Clerk/Railway previously absorbed (2026-07-13 restack, §18).

**What to build:**

- [ ] Python SDK: `start_agent_run` / `step` API, batch buffer, async flush, token capture
- [ ] LangGraph auto-instrumentation (`instrument_langgraph`, 3-line setup)
- [ ] Ingest API (Spring Boot): `POST /v1/ingest/runs`, Bean Validation of step graphs, cost computation at ingest, raw payloads to MinIO
- [ ] Postgres job queue: `analysis_jobs` table, claim SQL, retry/backoff/dead-job semantics (§10)
- [ ] Verdict worker (Stage 1, Python): per-step fan-out, Haiku judge with cached contract prompts, atomic run counter
- [ ] Built-in step contracts: `retrieval`, `llm`, `tool` (customers cannot customize yet)
- [ ] Failure taxonomy v1 (the 8 classes in §10)
- [ ] Localization pass (Stage 2): deterministic graph walk + Sonnet escalation with evidence requirement
- [ ] `GET /v1/runs/:run_id/diagnosis` endpoint
- [ ] Dashboard (React SPA): failed-run list → run timeline → diagnosis view (origin step highlighted, failure class, evidence, wasted cost)
- [ ] Diagnosis feedback button ("fix landed here? yes/no") → `diagnoses.confirmed_by_user`
- [ ] Auth (Spring Security): sign up, org creation, JWT sessions, hashed API key issuance, tenant context + RLS wiring (§9)
- [ ] VPS deployment: Docker Compose (nginx, api, worker, Postgres, MinIO), TLS via certbot, GitHub Actions deploy pipeline
- [ ] Backups: nightly pg_dump + MinIO mirror to Storage Box, weekly restore test
- [ ] Observability: GlitchTip + Prometheus/Grafana/Loki containers, Uptime Kuma on the nano-VPS

**What NOT to build in Phase 1:**
- TypeScript SDK (agent teams are Python-first; TS follows demand in Phase 2)
- Custom step contracts (built-ins only)
- CI integration of any kind (Phase 3 — needs the diagnosis corpus first)
- Failure clustering and cost dashboards (per-run cost display only)
- Eval suites, rubrics UI, baselines
- Stripe billing

**Design partner criteria:** Teams running a multi-step agent (5+ steps) in production that fails in ways they can't diagnose quickly. Ideal: LangGraph or custom Python agent, 5–20 engineers, real users generating real failures weekly.

**Success metrics (both must hold):**
1. Each partner receives 10+ diagnoses/week without manual intervention from you
2. **Fix-rate agreement > 70%:** when partners fix a diagnosed failure, the fix lands at the step Slate named. This is the product's core promise — if it can't clear 70% after 8 weeks of iteration, revisit the direction (see §18).

---

### Phase 2 — Monetization (Weeks 13–20)

**Goal:** First $1K MRR. Prove someone pays for diagnoses.

**What to build:**

- [ ] Stripe billing: usage-based on diagnosed runs, free / $99 / $499 tiers (§15)
- [ ] Usage metering: count diagnosed runs per org per billing period
- [ ] Custom step contracts (YAML editor UI + write-time validation)
- [ ] TypeScript SDK (same surface as Python)
- [ ] Failure clustering: embed failure signatures (origin step + class + evidence), group recurring failures via pgvector — "retrieval_miss at fetch_docs: 40% of this week's failures"
- [ ] Cost-per-failure analytics: dollars burned per failure class / agent / week (the Option-A payoff begins)
- [ ] Run explorer: browse/filter runs by agent, version, status, failure class, cost
- [ ] Slack alerts: new diagnosis, new failure cluster
- [ ] Org management UI: invite team members (email invites), manage API keys, roles

**Success metric:** 10 paying customers, $1K MRR, < 5% monthly churn, fix-rate agreement > 75%.

---

### Phase 3 — Growth (Months 5–9)

**Goal:** $10K MRR. Add regression protection and the full cost-per-quality surface.

**What to build:**

- [ ] Failure-derived regression suites: one-click "add to replay set" on any diagnosis; replay sets re-run against new agent versions
- [ ] GitHub Actions gate (`Slate/action@v1`): replay diagnosed failures on PR, fail if a known failure regresses or a new origin fault appears — the CI stickiness moat, earned from the diagnosis corpus
- [ ] Cost-per-quality dashboards: cost vs failure rate per agent version / model — "this model swap saved $X/month and cut retrieval misses by Y%" (Option A fully landed)
- [ ] Framework coverage: CrewAI, OpenAI Agents SDK, Claude Agent SDK auto-instrumentation + raw OTel bridge
- [ ] Success-run baselining: per-step score baselines from sampled successful runs, drift alerts
- [ ] SSO: OIDC via Spring Security; add self-hosted Keycloak if/when a deal demands SAML
- [ ] Team roles and permissions (viewer / developer / admin)

**Success metric:** $10K MRR, at least 3 customers at $499+/mo, ≥50% of customers using replay sets in CI, NPS > 50.

---

### Phase 4 — Scale ($50K MRR target)

**Goal:** Enterprise-ready. Hire first engineer.

**What to build:**

- [ ] Vertical failure taxonomies + contract packs: legal (citation accuracy), healthcare (safety), finance (compliance)
- [ ] On-premise / VPC deployment option
- [ ] SLA + uptime guarantees
- [ ] Migrate backend to AWS (ECS + RDS Aurora + ElastiCache + SQS)
- [ ] ClickHouse for analytics at billions-of-steps scale
- [ ] Dedicated support tier

---

## 15. Monetization

> **⚠ Changed for the agent-debugging pivot:** the billing unit moves from eval jobs to **diagnosed runs** — the unit the customer feels value from (one diagnosis ≈ one debugging session saved). Structure (usage-based, free/Pro/Growth/Enterprise, Stripe metered billing) is unchanged. Tier volumes below assume ~$0.014–0.02 blended COGS per diagnosed run (§8) and need validation against real step counts.

### Pricing Model

Usage-based billing on diagnosed runs, with a seat-based minimum for the dashboard.

| Tier | Price | Diagnosed runs | Target customer |
|------|-------|----------------|----------------|
| Free | $0 | 100 runs/mo, 7-day retention | Individual developers, OSS projects |
| Pro | $99/mo | 1,500 runs/mo | Startups and small teams |
| Growth | $499/mo | 10K runs/mo | Scaling companies |
| Enterprise | Custom | Unlimited + replay sets + SSO | $50K MRR+ |

Overages on Pro/Growth: $0.06 per diagnosed run above the plan limit (~3–4x blended COGS). Steps per run capped at 50 on Pro (COGS guard, §8).

### Why Usage-Based on Diagnosed Runs

- Aligns revenue with COGS (judge calls scale with analyzed runs, not raw traffic — capture itself is free to the customer)
- The billable event maps to felt value: a diagnosis is an hour of log-reading avoided, so ROI is trivially arguable at $0.06–0.33/run effective price
- Natural land-and-expand: more agents in production → more failures analyzed → higher tier
- Low friction to start (free tier, instrument in an afternoon, first diagnosis same day)

### Stripe Setup

Use Stripe Metered Billing for diagnosed-run volume. At the end of each billing period:
1. Query `SELECT COUNT(*) FROM diagnoses WHERE org_id = ? AND created_at > billing_period_start`
2. Report to Stripe: `stripe.subscriptionItems.createUsageRecord(itemId, { quantity: count })`

This runs as a nightly cron job. Use idempotency keys on the Stripe call.

---

## 16. Open Source Strategy

### What to Open Source

**Open source from day one:**
- TypeScript SDK (`@Slate/sdk`)
- Python SDK (`Slate`)
- GitHub Actions integration
- CLI tool (`Slate` CLI for running Slate suites locally)
- Default rubric library (YAML definitions for common Slate criteria)

**Keep proprietary:**
- The Slate engine (worker, scoring pipeline, judge prompt templates)
- The dashboard
- The storage layer
- The CI webhook infrastructure

### Why This Split

The SDK lives in every customer's codebase. Open-sourcing it removes the "black box trust problem" that kills B2B developer tool adoption. Developers will inspect it, contribute to it, and write blog posts about it.

The engine is your moat. The value is in the scoring quality, the rubric library, the score storage, and the CI integration — none of which is exposed by open-sourcing the SDK.

### OSS Community Flywheel

1. Developer finds SDK on GitHub
2. Integrates in a weekend project
3. Writes "I added Slate CI to my LLM app in 30 minutes" blog post
4. Their company's infrastructure team reads it
5. Enterprise deal starts

Target: 500 GitHub stars before charging money.

---

## 17. Scaling Strategy

### When to Migrate Off the VPS

Trigger: $50K MRR or when a single enterprise deal requires it (VPC deployment, SOC 2, data residency).

Interim step before AWS: split to two or three VPSes (workers on their own box, Postgres on its own box) — same compose files, no rearchitecture.

**AWS migration path:**

| Self-hosted (VPS) | AWS Equivalent |
|-------------------|---------------|
| Spring Boot API container | ECS Fargate (auto-scaling) |
| Python worker containers | ECS Fargate (queue can stay in Postgres, or move to SQS if throughput demands) |
| Self-hosted Postgres | RDS Aurora PostgreSQL |
| MinIO | S3 (same client code — swap endpoint) |
| Nginx + certbot | ALB + ACM |
| Prometheus/Grafana/Loki, GlitchTip | Keep self-hosted on ECS, or CloudWatch if ops budget allows |

**Database scaling path:**

1. Add read replica for dashboard queries (Postgres streaming replication)
2. Add connection pooling (PgBouncer) when connection count exceeds ~100
3. Partition `slate_jobs` and `traces` by `created_at` (TimescaleDB handles this)
4. If analytics queries slow down at billions of rows: add ClickHouse for the read path

**Diagnosis engine scaling:**

- Worker concurrency is the primary lever (currently 10 threads/container)
- Add worker containers via compose replicas — SKIP LOCKED makes claims safe at any worker count; move workers to a second VPS at CPU contention
- If the Postgres queue becomes a bottleneck (~1K jobs/sec sustained), that's the trigger to revisit the queue decision (§18) — not before
- Rate limit is Anthropic API quota — request limit increases at ~1M verdicts/day

### Performance Targets

| Metric | Phase 1 target | Phase 3 target |
|--------|---------------|----------------|
| Ingest API p99 latency | < 200ms | < 100ms |
| Slate job processing time (per job) | < 8s | < 5s |
| CI run (100 samples) total time | < 60s | < 30s |
| Dashboard page load | < 2s | < 1s |

---

## 18. Decision Log

Document key architectural decisions here as you make them. This prevents revisiting the same debate and explains context to future contributors (or future you).

```
Date: [initial draft]
Decision: Use Railway over AWS for initial deployment
Rationale: Solo founder. Railway gives full container control with zero ops overhead.
Trade-off: Less fine-grained control than AWS. Accept this until $50K MRR.
Revisit trigger: Enterprise customer requiring VPC / $50K MRR / infra engineer hire.
[2026-07-13 pivot check: held at pivot time.]
[2026-07-13 restack: BROKEN — superseded by the self-hosted full-control decision
 below. Founder requirement changed: no backend-as-a-service.]

Date: [initial draft]
Decision: Postgres over specialized DBs (Pinecone, ClickHouse)
Rationale: pgvector + TimescaleDB covers vector search and time-series at this scale.
Trade-off: Will hit Postgres limits at very high trace volume.
Revisit trigger: Dashboard queries > 2s, or traces table > 500M rows.
[2026-07-13 pivot check: HOLDS, but the revisit trigger arrives sooner — agent_steps
 grows 10–50 rows per run vs 1 per trace. Watch agent_steps row count from Phase 2;
 same 500M-row / 2s-query trigger, now applied to agent_steps.]

Date: [initial draft]
Decision: Claude Haiku as LLM judge
Rationale: $0.25/M input tokens vs $5/M for GPT-4o. 20x cheaper. Acceptable quality for rubric-based scoring.
Trade-off: Slightly lower quality on nuanced rubrics. Acceptable for v1.
Revisit trigger: Customer feedback that scores are consistently wrong.
[2026-07-13 pivot check: PARTIALLY BROKEN — single-judge-model assumption no longer
 holds. Superseded by the two-tier judging decision below. Haiku remains the Stage 1
 verdict judge; §8 cost model updated.]

Date: [initial draft]
Decision: Open-source SDKs, proprietary engine
Rationale: SDK trust drives adoption. Engine is the moat.
Trade-off: Community can fork the engine pattern. Acceptable — execution and data network effects are the real moat.
Revisit trigger: Never. This is the right structure long-term.
[2026-07-13 pivot check: HOLDS and strengthens — the open step-capture SDK (plus OTel
 compatibility) drives adoption; the diagnosis engine and accumulated fix-confirmed
 corpus stay proprietary. §16 language needs a light pass ("eval suites" → "step
 capture"), structure unchanged.]

Date: 2026-07-13
Decision: Pivot the wedge from eval/regression platform to step-level causal debugging
          for agent failures, with per-step cost attribution first-class from day one
Rationale: Head-on collision with Confident AI (YC W25) — identical OSS-SDK +
           proprietary LLM-judge-CI-gate architecture, 2-year head start, 16k+ star
           DeepEval, enterprise logos. Diagnosis is an orthogonal, underserved
           category; the existing judge pipeline repoints from final outputs to steps.
Trade-off: Localization is the hardest component and is new engineering. CI stickiness
           deferred to Phase 3 (failure-derived replay). Phase 1 grows to 10 weeks.
Revisit trigger: Fix-rate agreement < 70% after 8 weeks of design-partner iteration —
           if Slate can't reliably name the right step, the category claim fails.

Date: 2026-07-13
Decision: Two-tier judging — Haiku for per-step verdicts, Sonnet only for escalated
          localization (~30% of analyzed runs); deterministic graph walk handles the rest
Rationale: Verdicts are narrow, rubric-shaped tasks (Haiku territory). Whole-graph
           causal reasoning is not. Escalation-only keeps blended COGS ~$0.014/run.
Trade-off: Two prompts to maintain; escalation rate is a new COGS variable to monitor.
Revisit trigger: Escalation rate > 40% sustained, or escalated diagnoses disagree with
           user-confirmed fixes materially more than deterministic ones.

Date: 2026-07-13
Decision: Python SDK ships first; TypeScript deferred to Phase 2
Rationale: Agent frameworks (LangGraph, CrewAI, OpenAI Agents SDK) are Python-dominant;
           the wedge buyer runs Python. BREAKS the original Phase 1 ordering (TS first).
Trade-off: TS-only shops can't onboard in Phase 1. Acceptable — they're a minority of
           the wedge segment.
Revisit trigger: >30% of design-partner pipeline blocked on TS support.

Date: 2026-07-13
Decision: Retain eval-era tables (test_suites, slate_runs, slate_jobs, baselines,
          rubrics) rather than dropping them
Rationale: They power the Phase 3 failure-replay regression gate; rubrics are
          repurposed as step contracts. Avoids a destructive migration.
Trade-off: Schema carries dormant tables for two phases.
Revisit trigger: If Phase 3 replay design diverges enough that reuse costs more than
          a clean rebuild.

Date: 2026-07-13 (restack)
Decision: Self-hosted, full-control stack — Spring Boot API (Java 21), Python
          diagnosis workers, React SPA (Vite) behind Nginx, Docker Compose on a
          Hetzner VPS. No backend-as-a-service: Clerk, Railway, Vercel, BetterStack,
          and hosted Sentry all dropped. Stripe retained (payments only).
Rationale: Founder requirement: full backend control, founder-fluent technologies
          (Java/Spring, Python, React). Product design is stack-agnostic — the hard
          IP (contracts, verdicts, localization) is logic + API calls.
Trade-off: Auth/org/API-key management, TLS, deploys, and backup durability become
          your ops (~+2 weeks in Phase 1; backup restore-tests forever). Infra cost
          actually drops (~$35/mo vs ~$50).
Revisit trigger: Ops toil exceeding ~1 day/week, or an enterprise requirement that
          forces a cloud provider anyway ($50K MRR AWS path in §17 unchanged).

Date: 2026-07-13 (restack)
Decision: Postgres queue table (FOR UPDATE SKIP LOCKED) instead of Redis/BullMQ
Rationale: One less stateful service to operate. Enqueue is transactional with
          ingest writes (a run can never be half-enqueued). Retry/backoff/dead-job
          semantics are hand-owned columns, consistent with the hand-code rule.
Trade-off: Lower ceiling than a real broker; sub-second polling latency.
Revisit trigger: Sustained ~1K jobs/sec or visible claim contention — then SQS
          (post-AWS) or a broker.

Date: 2026-07-13 (restack)
Decision: Spring Security + own user/org/API-key tables instead of Clerk;
          Keycloak deferred until a deal demands SAML
Rationale: Full control requirement. OIDC/SSO is achievable in Spring Security
          when Phase 3 needs it; Keycloak adds a heavy service before it's earned.
Trade-off: Auth moves into the hand-code-carefully column (§13) — filter chain,
          key hashing, tenant context, and pool reset are now founder-owned risk.
Revisit trigger: First enterprise SAML requirement, or auth bugs eating >1 sprint.
```

---

*Last updated: 2026-07-13 — (1) repositioned from eval/regression platform to step-level agent debugger with first-class cost attribution; (2) restacked to a self-hosted, full-control stack: Spring Boot + Python workers + Postgres queue + MinIO + React SPA on a VPS, no backend-as-a-service (see §18 pivot and restack entries). Update this document when architectural decisions change, new competitive intelligence arrives, or phase scope is adjusted.*
