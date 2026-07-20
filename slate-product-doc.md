# Slate — Context Control Plane for AI-Assisted Repos
### Solo Founder Product Reference Document

> **Purpose:** This document is the single source of truth for building this product. It covers the why, what, how, and in what order. Reference it before every sprint. Update it as decisions change.

> **⚠ Repositioned 2026-07-15:** Slate is no longer a hosted step-level debugger for AI agents. It is a **repo-local context control plane** — a CLI that generates concise Markdown context beside the code, detects stale knowledge after changes, and surfaces what is safe to trust before the next AI action. The entire client-server stack (Spring Boot ingest API, Python diagnosis workers, Postgres/MinIO, React dashboard, VPS) was removed; the product is now a single dependency-free Python CLI. Rationale: the debugger wedge required production agent traffic and design partners before delivering any value, while the context-staleness pain is felt by every AI-heavy developer on day one, in every repo, with zero integration cost. See §3 for the new wedge and §14 for the decisions this breaks.

---

## Table of Contents

1. [The Idea & Why It Matters](#1-the-idea--why-it-matters)
2. [Market Opportunity](#2-market-opportunity)
3. [Product Strategy & Wedge](#3-product-strategy--wedge)
4. [Competitive Landscape](#4-competitive-landscape)
5. [Architecture Overview](#5-architecture-overview)
6. [Full Tech Stack](#6-full-tech-stack)
7. [Context Layer Design](#7-context-layer-design)
8. [Freshness Engine & Verification Score](#8-freshness-engine--verification-score)
9. [CLI Contract](#9-cli-contract)
10. [Build vs Vibecode Guide](#10-build-vs-vibecode-guide)
11. [Phase-by-Phase Build Plan](#11-phase-by-phase-build-plan)
12. [Monetization](#12-monetization)
13. [Open Source Strategy](#13-open-source-strategy)
14. [Decision Log](#14-decision-log)

---

## 1. The Idea & Why It Matters

### The Core Problem

AI coding workflows drift because the model starts every session from incomplete or outdated assumptions about the repo — its architecture, module boundaries, build rituals, and what is currently in flight. The human then pays a recurring tax: re-explaining the same context, fixing mistakes the AI made from stale assumptions, and maintaining scattered notes (CLAUDE.md, AGENTS.md, README fragments, Notion pages) that silently rot the moment code changes.

The failure mode is not that context files don't exist — every AI-heavy developer already keeps some. It's that **nothing tells you when they've gone stale.** A context file that was accurate two hundred commits ago reads exactly like one written this morning. The AI can't tell the difference, so it acts on the outdated version with full confidence. Stale context is worse than no context.

### The Specific Pains (Ranked by Acuteness)

**1. The AI acts on outdated assumptions**
The module map says the auth logic lives in `services/auth`; it moved three weeks ago. The AI confidently edits the wrong layer, and the human burns a review cycle catching it. No signal existed that the map was suspect.

**2. Repeated context re-explanation**
Every new session (or new tool, or new teammate) starts with the same ritual: "here's how this repo works, here's what I'm working on, don't touch X." The knowledge exists — it just isn't maintained anywhere the AI reliably reads first.

**3. Docs drift away from the code**
Context notes live in a wiki, a gist, a chat scrollback — anywhere but the repo. They don't travel through review, they don't change with the code, and nobody is on the hook for them. Six weeks in, they describe a project that no longer exists.

**4. No "current focus" handoff between sessions**
What was in flight yesterday? Which approach was already tried and rejected? Session N's hard-won context evaporates before session N+1. The AI re-litigates decided questions and re-attempts known dead ends.

**5. Trust is binary when it should be graded**
Today the choice is "feed the AI the context file" or "don't." There is no middle signal — *this doc is probably fine, that one is suspect, verify against the code first* — so humans either over-trust or hand-curate every session.

### Why This Is a Control Plane (Not a Docs Tool)

A docs generator produces artifacts. A **control plane** maintains a desired state and reports divergence. Slate's job is not to write beautiful documentation — it is to keep a small, opinionated context layer *provably aligned* with the code, and to make its trustworthiness legible (fresh / stale / needs-verification, plus a verification score) so both AI and human know what to rely on before acting. The freshness signal, not the prose, is the product.

---

## 2. Market Opportunity

### Market Size & Shape

There is no "AI context management" market line item yet — which is the point of a wedge. The proxies:

| Signal | Value |
|--------|-------|
| Developers using AI coding tools (2026) | ~80% of professional devs touch one weekly |
| AI coding tools market (2026) | ~$8B, fastest-growing dev-tools segment |
| `AGENTS.md` / `CLAUDE.md` convention adoption | de-facto standard across Claude Code, Cursor, Codex-style tools in under a year |
| Teams reporting "AI made changes based on stale docs/context" | recurring complaint in every AI-workflow survey and HN thread on the topic |

The convention layer (AGENTS.md et al.) proves the demand: developers already hand-maintain context files for AI. Nobody has shipped the *maintenance* layer — the thing that keeps those files true.

### Why Now

1. **Agentic coding went mainstream (2025–2026).** The unit of AI work moved from autocomplete to multi-file, multi-session tasks. Session-start context quality is now the dominant variable in output quality.
2. **The context-file convention already won.** AGENTS.md/CLAUDE.md means every AI tool has a well-known "read this first" hook. Slate doesn't have to create the behavior — only keep the files it feeds honest.
3. **Context windows grew, discipline didn't.** Dumping the repo into the window is slow, expensive, and still misses tribal knowledge (decisions, current focus, invariants). Concise maintained context beats brute force on cost and accuracy.

### Target User

**Primary:** solo developers and 2–10-person teams using AI heavily on one active repo — the people who feel stale-context pain weekly and can adopt a CLI without procurement.

**Secondary:** platform teams at larger companies standardizing "how our repos talk to AI tools" (Phase 3+ — team dashboards, PR bots).

**Not yet:** enterprises wanting a knowledge graph over every internal system. Slate is deliberately one-repo, Markdown-only (see §3, "What Slate Is Not").

---

## 3. Product Strategy & Wedge

### What Slate Is Not

- **Not a chat assistant.** Slate never talks to a model at runtime in the MVP; it maintains the files models read.
- **Not a generic documentation site.** No HTML, no hosting, no wiki. Markdown beside the code, reviewed like code.
- **Not a knowledge graph of every team system.** One repo, six files, ruthlessly concise.
- **Not a replacement for the codebase as source of truth.** The code stays canonical; Slate maintains a *human-readable layer above it* and — critically — tells you when that layer has diverged.

### The Wedge: A Freshness Signal for Repo Context

**The wedge:** Slate generates a small context layer (`AGENTS.md` + `.slate/*.md`), anchors every doc to the commit it last reflected, watches the code paths that can invalidate it, and derives a three-state freshness status plus a 0.00–1.00 verification score. Before the AI writes code, it reads the smallest useful context set *with trust labels*. After the change, `slate sync` re-aligns the layer so the next session starts from reality.

The core mechanism has three parts:

1. **Deterministic scan → concise context layer.** `slate init` scans the repo (languages, module map, entry points, build/test commands) and writes six opinionated Markdown files with clearly-marked auto-generated blocks and human-owned sections.
2. **Change detection.** Every doc's frontmatter records a *sync anchor* (commit SHA) and *watch globs* (the code whose changes can invalidate it). Status is derived, never stored: `fresh` (no watched change since anchor), `stale` (watched change landed — committed or uncommitted), `needs-verification` (anchor unresolvable after a rebase/squash — staleness is unknowable, which is worse than known-stale).
3. **Verification score.** A deterministic 0.00–1.00 trust signal per doc: do the paths the doc references still exist, how much watched code changed since the anchor, how far has the repo drifted. Cheap enough to run on every session start, honest enough to gate on in CI (`slate status --ci`).

### Why This Wedge

- **Value on day one, zero integration.** `pip install`, `slate init`, done. No SDK, no server, no API key, no design partners needed to prove value — unlike the debugger wedge this replaces.
- **It rides an existing convention instead of creating one.** AGENTS.md is already read by the major tools; Slate makes it trustworthy rather than asking anyone to change behavior.
- **The moat is workflow embedding, not IP.** Once the context layer lives in the repo, travels through PRs, and gates CI, ripping Slate out means losing the maintained layer and the freshness discipline. Same integration-depth moat as the old strategy, at 1% of the infrastructure.
- **Narrow enough for one person to own.** The MVP is ~1,500 lines of stdlib Python with a fully deterministic core. No COGS, no ops, no on-call.
- **Broad enough to expand.** IDE integrations, PR bots that flag "this change stales 3 context docs," team dashboards, LLM-assisted prose updates — all natural layers on top of a trusted freshness signal.

### MVP Value Promise

Before the AI writes or changes code, it reads the smallest useful context set — with per-doc trust labels. After the change, the context gets updated (or flagged), so the next session starts from reality instead of guesswork.

### Expansion Path

```
Phase 1 (Wedge — this repo, now)
└── CLI: init / status / sync / mark / verify / read
    └── Deterministic scan + generated context layer
    └── Freshness engine (fresh / stale / needs-verification)
    └── Verification score + --ci gate

Phase 2 (Assisted maintenance)
└── LLM-assisted prose updates on sync (scan stays the source of facts)
└── Watch inference from imports/dependency graphs
└── `slate diff`: what changed vs. what each doc claims
└── Pre-commit hook + PyPI release

Phase 3 (Team surface)
└── PR bot: "this PR stales architecture.md and modules.md" review comment
└── IDE/editor integration (status in the gutter, one-click sync)
└── Multi-repo support

Phase 4 (Control plane for teams)
└── Team dashboard: context health across repos
└── Policy: min verification score to merge
└── Hosted sync bot (the first paid server-side component)
```

---

## 4. Competitive Landscape

The field splits into three camps; none owns the freshness signal.

| Competitor | Strength | Gap You Exploit |
|------------|----------|-----------------|
| **Hand-maintained AGENTS.md / CLAUDE.md / .cursorrules** (the real incumbent) | Zero cost, universal convention, tool-native | Rots silently. No change detection, no staleness signal, no verification. Slate *upgrades* this workflow rather than competing with it — its output IS these files, kept honest. |
| **`/init`-style generators in AI tools** (Claude Code `/init`, Cursor rules generators) | One command, decent first draft | Write-once. No anchor to a commit, no watch model, no re-sync. The draft is stale the week after it's written, and nothing says so. |
| **Swimm** | Mature "docs coupled to code" product, IDE surface | Aimed at human documentation workflows in enterprises; heavyweight, not AI-session-first, not repo-local-CLI. No AI trust signal. |
| **Auto-doc generators** (RepoAgent-style LLM doc writers, mutable-style wiki builders) | Broad coverage, impressive demos | Generate *volume*, not a maintained concise layer. Verbose output is anti-value for context windows; no freshness state; regeneration is destructive to human edits. |
| **DeepWiki / repo-explainer sites** | Great for onboarding to unfamiliar OSS | External to the repo, read-only, generated on demand — doesn't travel with the code or through review, knows nothing about current focus or decisions. |
| **Memory features in AI tools** (Claude Code memory, Cursor memories) | Zero-effort capture | Per-tool, per-user silos. Not reviewable, not shared across tools or teammates, no tie to git state. Slate's layer is tool-agnostic and lives in the PR diff. |

**Your differentiation:**
- **The freshness signal is the product** — three derived states + a verification score, anchored to git. Nobody else answers "can I trust this doc right now?"
- **Human edits are first-class** — auto-blocks regenerate; everything else survives sync. Generators that clobber human prose never get adopted twice.
- **Concise by design** — six files, a fixed read order, a "read next" file for current focus. Optimized for context windows, not completeness.
- **Tool-agnostic** — output is plain Markdown at well-known paths; works with Claude Code, Cursor, Codex, and whatever ships next quarter.
- **Deterministic core** — same repo state → same status. Trust signals must not hallucinate; the MVP needs no LLM at all.

---

## 5. Architecture Overview

> **⚠ Rearchitected 2026-07-15:** the four-layer client-server system (ingest API → workers → Postgres/MinIO → React dashboard) is gone. Slate is now a single local CLI operating on the user's repo. There is no server, no database, no queue, and no network call in the MVP. All state lives in the repo itself — metadata in doc frontmatter, history in git.

```
┌────────────────────────────────────────────────────────────┐
│  User's repo (the only "deployment target")                │
│                                                            │
│  AGENTS.md            ◄─── routing + trust protocol        │
│  .slate/                                                   │
│  ├── read-next.md     ◄─── current focus (human-owned)     │
│  ├── architecture.md  ◄─┐                                  │
│  ├── modules.md       ◄─┤  generated: auto-block + human   │
│  ├── workflows.md     ◄─┘  sections, freshness frontmatter │
│  └── decisions.md     ◄─── append-only log (human-owned)   │
│                                                            │
│  .git/                ◄─── the freshness anchor store      │
└────────────────────────────────────────────────────────────┘
                 ▲                    ▲
                 │ reads first        │ init / status / sync /
                 │ (read order +      │ mark / verify / read
                 │  trust labels)     │
        ┌────────┴───────┐   ┌───────┴────────┐
        │  AI tool       │   │  slate CLI     │
        │  (Claude Code, │   │  (Python 3.11+,│
        │  Cursor, ...)  │   │  stdlib only)  │
        └────────────────┘   └────────────────┘

  CLI internals (slate/):
  scanner ──► generator ──► context docs
                 ▲              │
  gitutil ──► freshness ◄───────┘      globs ──► watch matching
                 │
              verify (score)          frontmatter (metadata I/O)
```

### Data Flow for One Working Cycle

1. `slate init` scans the repo (via `git ls-files` — gitignore-aware) and writes the six-doc context layer; every doc's frontmatter records watch globs and the HEAD commit as its sync anchor
2. The developer commits the layer; the AI tool reads `AGENTS.md` → the ordered docs, with `slate status` as the trust check
3. Code changes land (committed or just sitting in the working tree)
4. `slate status` diffs each doc's anchor against current state; changed paths are matched against watch globs; affected docs flip to `stale`
5. `slate sync` re-scans and rewrites only the marked auto-blocks (human sections untouched), re-anchoring the docs to HEAD; human-owned docs are reviewed and re-attested with `slate mark`
6. `slate verify` scores every doc 0.00–1.00; `slate status --ci` fails the build if the layer was left stale — context updates travel in the same PR as the code

Total latency target: every command < 1 second on a 10K-file repo (git plumbing + regex, no network).

---

## 6. Full Tech Stack

> **⚠ Restacked 2026-07-15:** the entire hosted stack (Spring Boot, Python workers, Postgres+pgvector+Timescale, MinIO, Nginx, Docker Compose, Hetzner VPS, GlitchTip/Prometheus/Grafana/Loki, Stripe) is removed. What remains is deliberately minimal and still honors the founder rule: no backend-as-a-service, full control — trivially satisfied, since there is no backend at all.

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.11+ | Founder fluency; ubiquitous on dev machines; 3.11 floor for `tomllib` |
| Runtime dependencies | **None** (stdlib only) | An always-on repo tool must never break a user's environment or lose a dependency-resolution fight. `argparse`, `re`, `subprocess`, `tomllib`, `json` cover everything |
| Dev dependencies | pytest | Tests build real throwaway git repos and run the CLI against them |
| State store | The repo itself | Freshness metadata in doc frontmatter (hand-rolled YAML subset); history queries via the `git` CLI. No hidden state — everything reviewable in the diff |
| Distribution | pip editable install now; PyPI (`pipx install slate-context`) in Phase 2 | Zero-friction adoption path |
| CI | GitHub Actions (one job: pytest + `slate status --ci` dogfood) | The repo gates itself with its own product |

**What this stack deletes from the old cost model:** the ~$35/mo infra baseline, judge COGS, backups, uptime monitoring, TLS, deploys — all gone. Pre-revenue burn is $0 plus a domain.

---

## 7. Context Layer Design

### The Doc Set (fixed, small, opinionated)

| Doc | Path | Ownership | Watches (default) | Job |
|-----|------|-----------|-------------------|-----|
| Agent routing | `AGENTS.md` | generated | `.slate/**` | Read order + trust protocol; the well-known entry point AI tools already look for |
| Read next | `.slate/read-next.md` | **human** | — | Current focus: what's in flight, landmines, tried-and-rejected. The session-to-session handoff |
| Architecture | `.slate/architecture.md` | generated | source dirs + build manifests | What the system is; invariants an AI must not break |
| Module map | `.slate/modules.md` | generated | source dirs | Where things live |
| Workflows | `.slate/workflows.md` | generated | Makefile, manifests, CI files | How to build/test/run |
| Decisions | `.slate/decisions.md` | **human** | — | Append-only decision log (this document's §14 pattern, exported to every repo) |

Six files, always the same names, always the same read order. Predictability is a feature: tools and humans learn the layout once.

### Generated vs Human-Owned

Generated docs contain one marked block:

```markdown
<!-- slate:auto — generated by `slate sync`; edit outside this block -->
| Module | Files | Primary language | Entry hints |
...
<!-- /slate:auto -->

## Notes (human)
Anything here survives every sync.
```

`slate sync` rewrites only the block. If a human deletes the markers, sync appends a fresh block rather than destroying their text. Human-owned docs (`read-next`, `decisions`) are never rewritten — Slate only tracks their freshness, and `slate mark` records a human attestation at the current commit.

### Freshness Frontmatter

Every doc opens with a tiny YAML-subset frontmatter block — flat keys plus one list, parsed by ~60 lines of hand-rolled stdlib code:

```markdown
---
slate_doc: modules
slate_generated: true
slate_synced_commit: 3f2c91a
slate_synced_at: 2026-07-15T18:04:00+00:00
slate_synced_digest: 9f2ab6c1d4e0837a
slate_watches:
  - slate/**
  - tests/**
---
```

Unknown keys round-trip untouched. The metadata is deliberately human-readable and diff-reviewable — the control plane has no hidden state.

---

## 8. Freshness Engine & Verification Score

> **This is your core IP. Hand-code the freshness derivation, the glob matcher, the git change detection, and the score. A false "fresh" is the one bug that destroys the product's promise — worse than any crash.**

### Freshness Derivation (never stored, always derived)

```
anchor := doc.slate_synced_commit

if anchor missing:
    → needs-verification         # metadata stripped — staleness unknowable

if anchor unresolvable (rebase/squash-merge):
    # content-digest fallback: the anchor died, the content didn't
    if doc.slate_synced_digest matches a fresh digest of the watched files:
        → fresh (content-verified; `slate sync` re-anchors)
    elif digest recorded but mismatched:
        → stale (watched content changed; working-tree paths as evidence)
    else:
        → needs-verification     # pre-digest layer — truly unknowable

changed := git diff --name-only anchor..HEAD
         ∪ working-tree changes (git status --porcelain, incl. untracked + renames)
         − all context-doc paths  # docs never invalidate docs; only code counts

hits := changed paths matching doc.slate_watches
if no hits:
    → fresh
elif doc is generated
     and regenerating the auto-block from a fresh scan reproduces what's on disk
     and no human-written section references a hit:
    → fresh (content-verified — the change provably didn't invalidate the doc)
else:
    → stale (with the offending paths as evidence)
```

Design rules baked into the engine:

- **Uncommitted changes count.** The AI acts on the working tree, not on HEAD — staleness must too.
- **Editing a context doc never stales the layer.** Humans improving docs (and Slate syncing them) is desired behavior; only *code* changes invalidate.
- **Unknowable ≠ fresh.** A lost anchor degrades to `needs-verification`, never silently to `fresh` — but *provable* beats unknowable: the content digest (`slate_synced_digest`, recorded at every sync/mark) lets a squash-merge or rebase recover to `fresh` when the watched content demonstrably matches the last sync. Squash-merge is the dominant team workflow; it must not degrade the whole layer to a rumor.
- **`stale` means "the doc's claims are actually in question."** Watch globs are deliberately broad, so most edits inside a watched tree don't change what a doc claims (editing a function body never moves a module). When the regenerated auto-block is byte-identical to what's on disk and no hand-written claim references a changed path, the doc is `fresh (content-verified)` — with the changed paths still attached as evidence. A signal that fires on half of all commits is a signal people learn to ignore; content verification keeps `stale` meaning "sync would change something."
- **Verification is conservative by construction.** Anything unprovable — missing auto-block markers, a human section referencing a changed path, a digest mismatch — stays `stale`. A false `fresh` remains the catastrophic bug.
- **Watch globs use `**` semantics** compiled to regex by hand (fnmatch has no `**`) — `slate/**`, `**/conftest.py`, `docker-compose*` all mean what a gitignore-literate developer expects.

### Verification Score (0.00–1.00 per doc)

Three weighted, fully deterministic components:

| Component | Weight | Signal |
|-----------|--------|--------|
| Reference validity | 0.50 | Fraction of repo paths the doc mentions (markdown links + backticked paths) that still exist. A doc pointing at deleted files is actively misleading |
| Watch quiet | 0.35 | 1.0 with no watched changes since the anchor, −0.1 per changed path |
| Anchor drift | 0.15 | Decays 0.02 per commit landed since the anchor — old attestations are weaker, even when no watched path changed |

Content verification feeds the score the same way it feeds the status: a content-verified doc takes no watch-quiet penalty (the changes provably didn't touch its claims). A doc with an orphaned anchor is scored by what the digest can prove — digest match: full scoring; digest mismatch: known-stale, only references count (`0.5 × reference validity`); no digest recorded: **capped at 0.25**, because unverifiable is never trustworthy. Thresholds are advisory in the MVP (the human/AI reads the score); Phase 4 makes "min score to merge" a team policy.

### Why No LLM in the Core

Scores and statuses must be reproducible, explainable, and free. Same repo state → same output, every time, in milliseconds. LLM-written *prose* arrives in Phase 2 — but it writes into auto-blocks whose facts come from the deterministic scan, and it never touches the trust math.

---

## 9. CLI Contract

```
slate init [--force]        scan repo, generate the context layer
                            (refuses to clobber an existing layer without --force)
slate status [--json|--ci]  freshness per doc; --ci exits 1 if anything isn't fresh
slate sync [DOC...]         regenerate auto-blocks, re-anchor to HEAD
                            (default: generated docs only; human docs are listed as
                             untouched with a nudge to review + mark)
slate mark DOC...           human attestation: doc is accurate at HEAD
slate verify [--json]       verification score per doc, with missing-path evidence
slate read [--paths]        the ordered first-read path with trust labels
                            (--paths = machine-consumable file list)

# Phase 2
slate diff [DOC...]         per suspect doc: watched changes with kinds (A/M/D/R),
                            broken claims (referenced paths that no longer exist),
                            and a unified-diff preview of what sync would rewrite
slate sync --prose          opt-in LLM orientation paragraph above the scanned
                            facts (ANTHROPIC_API_KEY required; prose failures
                            never block the deterministic sync)
slate watches [--apply]     current watch globs + proposed additions inferred
                            from import graphs and doc body references
slate hook install|uninstall  pre-push gate running `status --ci` (pre-PUSH, not
                            pre-commit — see the 2026-07-15 hook decision)

# Phase 3
slate fleet [PATH...] [--ci]  freshness roll-up across repos (a path is a repo,
                            or a parent scanned one level deep)

# Agent integration (2026-07-16)
slate mcp [--access read|full]  run the MCP server (stdio JSON-RPC) so coding
                            agents call slate themselves; --access overrides
                            the repo mode for one session
slate agent enable CLIENT [--full]  register the MCP server with claude
                            (.mcp.json), cursor (.cursor/mcp.json), or all;
                            --full also raises the access ceiling
slate agent access [read|full]  get/set the agent access ceiling
                            (.slate/agent-access — committable team policy)
slate agent status [--json] wiring + access mode
```

**MCP tools** (same shapes as the `--json` CLI output; no trust math in the server):
read access exposes `slate_read` (ordered docs + trust labels + scores + contents),
`slate_status`, `slate_verify`, `slate_diff`. Full access adds `slate_sync`,
`slate_mark`, `slate_update_focus` (rewrites read-next's Current focus/Landmines),
`slate_append_decision`. **Two consent layers, Claude Code-style:** the client
prompts per tool call (until always-allowed); Slate's access mode is the hard
ceiling underneath — in read mode the mutating tools are not even listed, and a
toggle takes effect mid-session without restarting the server.

**Exit codes:** `0` ok · `1` freshness problems found (`status --ci`) · `2` usage/environment error (not a git repo, unknown doc, no layer).

**Contract stability:** `--json` output shapes and exit codes are the API — AI tools and CI scripts will consume them. Breaking either after v0.1 requires a major version. Human-readable output is explicitly *not* stable.

### The AI Session Protocol (what AGENTS.md instructs)

1. Session start: call `slate_read` (MCP) — or run `slate status` and read in the printed order — weighting trust by status
2. `stale` → verify claims against code before acting (or sync)
3. `needs-verification` → treat the doc as a rumor
4. After the task: `slate_update_focus`, `slate_append_decision` if a real call was made, then `slate_sync` — or the CLI equivalents — and commit context changes with the code

With the MCP server wired (`slate agent enable`), the agent performs this whole loop itself; the human only answers the editor's permission prompts (or grants full access once).

---

## 10. Build vs Vibecode Guide

**Hand-code (bugs are silent, and trust is the product):**
- Freshness derivation (`freshness.py`) — a false `fresh` is catastrophic
- Watch-glob → regex compilation (`globs.py`) — a pattern that under-matches silently under-reports staleness
- Git change detection (`gitutil.py`) — renames, untracked files, unborn branches, unresolvable anchors
- Verification scoring and its weights (`verify.py`)
- Frontmatter round-tripping (`frontmatter.py`) — losing a human's metadata or key ordering corrupts the layer
- Auto-block boundary logic (`context.replace_auto_block`) — one off-by-one eats someone's hand-written docs

**Vibecode freely:**
- Doc templates and generated prose scaffolding
- CLI presentation (tables, icons, bars)
- Scanner heuristics for additional languages/build systems
- New `--json` fields (additive only)

**The test invariant:** every hand-code module gets tests against *real throwaway git repos* (see `tests/conftest.py`), not mocks — git's actual behavior around renames, quoting, and empty repos is the spec.

---

## 11. Phase-by-Phase Build Plan

### Phase 1 — MVP (done in this repo)

**Goal:** the core loop works end to end on one repo, deterministic, tested.

- [x] Repo scanner (languages, module map, entry hints, commands, CI)
- [x] Context layer generation with auto-blocks + human sections
- [x] Freshness frontmatter + hand-rolled parser
- [x] Freshness engine: fresh / stale / needs-verification, uncommitted changes included
- [x] Verification score with missing-reference evidence
- [x] CLI: init / status / sync / mark / verify / read, `--json`, `--ci`
- [x] Test suite on real git repos; CI dogfoods `slate status --ci`
- [x] Slate's own context layer maintained by Slate

### Phase 2 — Assisted maintenance (built 2026-07-15)

**Goal:** syncs get smarter; distribution gets real.

- [x] Release automation: `release.yml` publishes to PyPI on `v*` tags via trusted publishing. *(One-time owner setup left: create the `slate-context` project + trusted publisher on pypi.org, then tag `v0.2.0`.)*
- [x] Local hook (`slate hook install`, plus `.pre-commit-hooks.yaml` for the pre-commit framework) — runs at **pre-push**, not pre-commit (see decision log)
- [x] `slate diff` — watched changes with kinds, broken claims, and a unified-diff preview of what sync would rewrite
- [x] Watch inference (`slate watches [--apply]`): proposals from Python/JS/TS import edges and doc body references; additions are suggested, never silently applied
- [x] Optional LLM-assisted prose (`slate sync --prose`): opt-in, urllib-only, injectable transport; facts stay deterministic and prose failures never block the sync

### Phase 3 — Team surface (built 2026-07-15)

**Goal:** the freshness signal reaches reviews and editors.

- [x] GitHub PR bot: reusable composite action at the repo root (`uses: gurbirdhaliwal/slate@v0.2.0`) — posts an idempotent PR comment (statuses, scores, changed paths, broken claims), optional fail-on-stale; dogfooded in this repo's CI
- [x] Editor integration: VS Code extension (`integrations/vscode/`, plain JS, no build step) — file-tree trust badges, status-bar roll-up, one-click sync. *(Marketplace publishing optional; installs from a local VSIX today.)*
- [x] Multi-repo roll-up: `slate fleet [PATH...] [--json] [--ci]`
- [x] Agent integration (added 2026-07-16): MCP server (`slate mcp`, stdlib stdio JSON-RPC) + `slate agent enable/access/status` + VS Code access toggle — the agent runs the whole read→verify→sync loop itself under a read-default capability ceiling

### Phase 4 — Control plane for teams (first revenue)

**Goal:** the team layer becomes the paid product.

- [ ] Team dashboard: context health across repos, staleness trends, score-over-time
- [ ] Merge policy: minimum verification score / no-stale-docs gates as an installable check
- [ ] Hosted sync bot (first server-side component — and the first infra cost since the pivot)

---

## 12. Monetization

> **⚠ Rebuilt for the pivot:** usage-based billing on diagnosed runs is gone (there are no runs and no COGS). The model is open-core: the CLI is free forever; teams pay for the coordination layer.

| Tier | Price | What's paid |
|------|-------|-------------|
| CLI (forever) | $0 | Everything in Phases 1–2. Adoption is the moat; charging for the wedge kills it |
| Team | ~$10/user/mo | Phase 3/4: PR bot, merge policies, team dashboard, multi-repo roll-up |
| Enterprise | Custom | SSO, audit, policy controls, private hosting of the bot |

**Why open-core here:** the CLI produces value alone, so it spreads bottom-up like prettier/eslint did; the *team* pain (is everyone's context layer healthy? can we gate merges on it?) is organizational, budget-holding, and naturally server-side. Revenue starts in Phase 4; until then burn is ~$0, which the solo-founder cost structure now actually permits.

---

## 13. Open Source Strategy

**Open source from day one:** the entire CLI — scanner, freshness engine, verification score, templates. The trust math *must* be inspectable: "how does it decide what's fresh?" cannot be a black box, or AI tools and skeptical developers won't build on the signal.

**Keep proprietary (later):** the hosted team layer — PR bot service, dashboards, policy enforcement. The classic open-core line: the single-player tool is open, the multiplayer coordination is paid.

### OSS Flywheel

1. Developer feels stale-context pain, finds `slate init` on GitHub/HN
2. Context layer lands in their repo; teammates and their AI tools see `AGENTS.md` + trust protocol in every session
3. The layer travels through PRs — every reviewer is exposed to the freshness statuses
4. Team wants the PR bot and the dashboard → Phase 4 conversion

Target: the freshness frontmatter keys (`slate_synced_commit`, `slate_watches`, statuses) become a convention other tools read — at which point Slate is infrastructure, not a tool.

---

## 14. Decision Log

Document key architectural decisions here as you make them. This prevents revisiting the same debate and explains context to future contributors (or future you).

```
Date: [initial draft]
Decision: Use Railway over AWS for initial deployment
[2026-07-13 restack: BROKEN — superseded by the self-hosted decision.]
[2026-07-15 pivot check: MOOT — there is no deployment. The product is a local CLI.]

Date: [initial draft]
Decision: Postgres over specialized DBs (pgvector + Timescale on one engine)
[2026-07-15 pivot check: MOOT — no database. All state lives in doc frontmatter
 and git. If the Phase 4 team layer needs a store, decide then; nothing carries over.]

Date: [initial draft]
Decision: Claude Haiku as LLM judge (two-tier Haiku/Sonnet after 2026-07-13)
[2026-07-15 pivot check: BROKEN — the MVP has no LLM calls at all. The freshness
 engine is deliberately deterministic (§8). LLM returns in Phase 2 for prose only,
 never for trust math. Model choice deferred to then.]

Date: [initial draft]
Decision: Open-source SDKs, proprietary engine
[2026-07-15 pivot check: INVERTED — the engine (freshness/verification) is now the
 open part, because the trust signal must be inspectable to be adopted. The paid
 boundary moves to the hosted team layer (§13). The open-core structure survives;
 the line moved.]

Date: 2026-07-13
Decision: Pivot the wedge from eval/regression platform to step-level agent debugging
[2026-07-15 pivot check: SUPERSEDED by the context-control-plane pivot below. The
 debugger required production traffic and design partners before first value; it
 never left the skeleton stage.]

Date: 2026-07-13 (restack)
Decision: Self-hosted full-control stack (Spring Boot + Python workers + Postgres
          queue + MinIO + React SPA on a Hetzner VPS), no backend-as-a-service
[2026-07-15 pivot check: MOOT as infrastructure (all of it deleted), but the
 founder rule it encoded — full control, no BaaS — HOLDS and is now trivially
 satisfied: there is no backend. Revisit only at Phase 4 (hosted team layer),
 where the same rule applies to whatever gets built.]

Date: 2026-07-13 (restack)
Decision: Postgres queue table (SKIP LOCKED) instead of Redis/BullMQ
[2026-07-15 pivot check: MOOT — no queue, no workers, no jobs.]

Date: 2026-07-13 (restack)
Decision: Spring Security + own auth tables instead of Clerk
[2026-07-15 pivot check: MOOT — no auth surface. A CLI on the user's machine has
 no accounts. Auth re-enters at Phase 4 with the hosted layer.]

Date: 2026-07-15
Decision: Pivot from hosted step-level agent debugger to repo-local context control
          plane — CLI + Markdown context layer + freshness signal + verification score
Rationale: The debugger wedge needed production agent traffic, instrumented design
           partners, and a full hosted stack before delivering any value — a long,
           capital-shaped runway for a solo founder. Stale-context pain is felt by
           every AI-heavy developer immediately, in every repo; the AGENTS.md
           convention already created the read-first hook; nobody owns the
           freshness/maintenance layer. Value on day one, $0 infra, no COGS.
Trade-off: Smaller initial revenue surface (open-core, revenue deferred to Phase 4)
           vs. usage-based billing. The hosted stack's engineering is discarded
           (the skeleton was two days old — cheap to walk away from).
Revisit trigger: If after ~8 weeks of real usage the freshness signal doesn't
           change behavior (users ignore stale flags / don't run sync), the trust
           thesis fails and the wedge needs rethinking.

Date: 2026-07-15
Decision: Stdlib-only Python CLI, zero runtime dependencies
Rationale: A context tool must be installable into any repo/environment without
           dependency-resolution risk, and must start in milliseconds. Everything
           needed (argparse, re, subprocess, tomllib, json) is in the stdlib.
Trade-off: Hand-rolled frontmatter parsing (YAML subset) and glob matching instead
           of PyYAML/pathspec — ~120 extra lines, fully tested.
Revisit trigger: A real need for full YAML in frontmatter, or gitignore-style
           negation in watch patterns.

Date: 2026-07-15
Decision: Freshness status is derived at read time, never stored; anchored to git
Rationale: Stored status can lie (nothing invalidates it); derived status is always
           consistent with repo state. Git is already the change ledger — anchoring
           to a commit SHA gives change detection for free, including uncommitted
           work via the working tree.
Trade-off: Requires a git repo (slate refuses to run outside one); rebases/squashes
           orphan anchors — handled as needs-verification, never silently fresh.
Revisit trigger: Meaningful demand from non-git users (unlikely in the target
           segment).

Date: 2026-07-15
Decision: No LLM in the MVP; deterministic scan and trust math only
Rationale: Trust signals must be reproducible, explainable, and free. An LLM that
           hallucinates a module map poisons the exact thing the product exists to
           protect. Facts come from the scan; the LLM (Phase 2, opt-in) only ever
           phrases prose inside auto-blocks.
Trade-off: Generated docs are drier than LLM prose; human sections carry the
           narrative until Phase 2.
Revisit trigger: Phase 2 — and even then, never for status/score computation.

Date: 2026-07-15 (Phase 2/3 build)
Decision: The local freshness gate is a pre-PUSH hook, not pre-commit
Rationale: The sync workflow is inherently two commits — commit the code, then
           `slate sync` anchors the docs to that commit and the doc updates are
           committed on top. A pre-commit `status --ci` fails exactly when
           committing the code, blocking the legitimate workflow. Pre-push
           checks the branch tip, which is the same contract CI enforces.
Trade-off: Staleness is caught at push time, not commit time — a few minutes
           later in the loop.
Revisit trigger: If anchoring ever moves from commits to content hashes (which
           would make same-commit sync possible), reconsider pre-commit.

Date: 2026-07-15 (Phase 2/3 build)
Decision: LLM prose is a callback injected into sync, over raw urllib, opt-in
          via --prose + ANTHROPIC_API_KEY; prose failure degrades to a plain sync
Rationale: Keeps zero runtime dependencies, keeps generator testable without a
           network (injectable transport), and keeps the §8 boundary mechanical:
           the LLM can only prepend prose above facts it was handed — it cannot
           touch facts, statuses, or scores by construction.
Trade-off: No SDK conveniences (retries, streaming); acceptable for one short
           completion per generated doc.
Revisit trigger: Prose expands beyond one paragraph per doc, or needs models
           that require more elaborate request handling.

Date: 2026-07-15 (Phase 2/3 build)
Decision: Integrations ship in-repo and thin: a composite GitHub Action at the
          repo root (pip-installs the action checkout, comments via REST), and
          a plain-JS no-build VS Code extension that renders `status --json`
Rationale: One repo to version; the action needs no marketplace approval to be
           usable (`uses: gurbirdhaliwal/slate@tag`); the extension stays pure
           presentation so all trust math remains in the tested CLI.
Trade-off: Composite action installs Python deps on every run (~seconds);
           extension unpublished until a marketplace account exists.
Revisit trigger: The bot needing state beyond a PR comment (that's the Phase 4
           hosted layer, not a bigger action).

Date: 2026-07-15
Decision: Fixed six-doc context layer with fixed names and read order
Rationale: Predictability beats configurability for a convention: tools and humans
           learn one layout; AGENTS.md routing stays trivial; docs stay concise
           because scope per file is defined.
Trade-off: Repos with unusual shapes can't restructure the layer (they can still
           add arbitrary human content within each doc).
Revisit trigger: Repeated field evidence that a seventh doc (e.g. API surface,
           data model) is being crammed into Notes sections across many repos.

Date: 2026-07-16
Decision: Agent integration via an MCP stdio server with a two-layer consent
          model — the client owns per-call permission prompts (Claude Code
          pattern); Slate owns a read-default capability ceiling in
          .slate/agent-access that gates which tools even exist.
Rationale: Users shouldn't ferry CLI output into the chat by hand. MCP is the
          convention every major coding agent already speaks, and stdio JSON-RPC
          is implementable in ~100 lines of stdlib (keeps the zero-dependency
          rule). Reimplementing permission UX inside Slate would fight the
          editor; but relying on editor prompts alone makes one careless
          "always allow" irreversible — the server-side ceiling caps the blast
          radius, is diff-reviewable, and can be committed as team policy.
Trade-off: Two config surfaces (editor allowlists + .slate/agent-access) to
          explain. Write tools re-read the ceiling per call so toggles apply
          mid-session, costing one file read per call (negligible).
Revisit trigger: MCP spec churn breaking stdio framing, or field evidence that
          read-default friction stops users from ever granting full access.

Date: 2026-07-20
Decision: `stale` requires that the change actually put the doc's claims in
          question — when regenerating the auto-block reproduces what's on disk
          and no human-written section references a changed path, the doc stays
          `fresh (content-verified)`, with the changed paths kept as evidence.
Rationale: Premortem finding #1 (alarm fatigue): watch globs are deliberately
          broad, so ~half of all commits flagged some doc even when nothing the
          doc claims had changed. A signal that is always yellow carries no
          information, and the sync ritual it demands becomes noise people
          disable. Content verification is deterministic (same scan, same
          bytes), so it costs no trust: `stale` now means "sync would change
          something, or a hand-written claim may be affected."
Trade-off: `slate status` may now run a repo scan (only when watched paths
          changed); still sub-second and local. Prose-synced docs verify on
          the facts below the prose paragraph only.
Revisit trigger: Any observed false `fresh` — a content-verified doc whose
          human prose was in fact invalidated by a change the reference check
          didn't catch. That would force tightening (e.g. staling on any
          human-section reference into a changed *directory*).

Date: 2026-07-20
Decision: Every sync/mark records `slate_synced_digest` — a sha256 fingerprint
          of the watched files' content — and an unresolvable commit anchor
          falls back to it: digest match → fresh (re-anchor via sync), mismatch
          → stale, no digest → needs-verification as before.
Rationale: Premortem finding #2: anchors are commit SHAs, and squash-merge —
          the default merge mode on GitHub — orphans them. Without the fallback,
          every squash-merged PR degraded the entire layer to needs-verification
          (score capped at 0.25) in every fresh clone and CI checkout: the
          product's steady state in a normal team workflow was its own worst
          case. The digest survives any history rewrite because it anchors to
          content, not to the commit graph. This is the "content hashes"
          revisit trigger from the 2026-07-15 pre-push hook decision, half
          taken: commits remain the primary anchor (cheap range diffs, path
          evidence), content is the recovery path.
Trade-off: One extra frontmatter key; stamping hashes the watched files
          (~milliseconds). A digest mismatch can't enumerate committed changed
          paths (no anchor to diff against) — evidence degrades to working-tree
          changes plus `slate diff`'s sync preview.
Revisit trigger: Repos big enough that hashing watched files on sync is felt
          (>1s), or field demand for same-commit sync — the digest makes a
          content-primary anchor possible if commits keep proving too fragile.
```

---

*Last updated: 2026-07-20 — freshness engine hardened against its two premortem failure modes: (1) content verification — `stale` now requires that a change actually alters the doc's claims (regenerated auto-block differs, or a human section references a changed path), killing the alarm-fatigue noise of broad watch globs; (2) `slate_synced_digest` content fallback — squash-merge/rebase no longer degrades the layer to `needs-verification` when the watched content provably matches the last sync (see §8 and the 2026-07-20 decisions in §14). Previously 2026-07-16 — added agent integration (MCP server, access ceiling, editor toggle); previously 2026-07-15 — (1) repositioned from hosted step-level agent debugger to repo-local context control plane: CLI + Markdown context layer + git-anchored freshness engine + deterministic verification score; entire hosted stack removed (see §14 pivot entries). (2) Phases 2 and 3 built: `slate diff`, pre-push hook + pre-commit-framework support, watch inference, opt-in LLM prose, PyPI release automation, GitHub PR bot action, VS Code extension, `slate fleet` (see §9, §11, and the 2026-07-15 build entries in §14). Update this document when architectural decisions change, new competitive intelligence arrives, or phase scope is adjusted.*
