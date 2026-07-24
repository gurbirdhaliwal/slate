---
slate_doc: decisions
slate_generated: false
slate_synced_commit: 8d4e03e
slate_synced_at: 2026-07-24T18:59:11+00:00
slate_synced_digest: e3b0c44298fc1c14
slate_watches:
---

# Decision log

Append-only. One entry per decision that a future reader (or AI)
would otherwise re-litigate.

```
Date: YYYY-MM-DD
Decision:
Rationale:
Trade-off:
Revisit trigger:
```

The full strategic log lives in `slate-product-doc.md` §14; entries here are
the repo-level calls an AI session needs at hand.

```
Date: 2026-07-15
Decision: Pivot — Slate is a repo-local context control plane CLI; the entire
          hosted stack (Spring API, workers, Postgres, dashboard) was deleted.
Rationale: Stale-context pain is universal and day-one; the debugger wedge
          needed production traffic before delivering value.
Trade-off: Revenue deferred to the team layer (Phase 4).
Revisit trigger: Freshness signal doesn't change user behavior after ~8 weeks.

Date: 2026-07-15
Decision: Zero runtime dependencies; freshness derived from git at read time,
          never stored; no LLM anywhere in the trust math.
Rationale: Trust signals must be reproducible, explainable, and free.
Trade-off: Hand-rolled frontmatter + glob matching (~120 lines, tested).
Revisit trigger: Real need for full YAML or gitignore-style negation.

Date: 2026-07-15
Decision: The local freshness gate is a pre-PUSH hook, not pre-commit.
Rationale: Syncing is two commits (code, then re-anchored docs); a pre-commit
          gate fails exactly when committing the code. Push time checks the
          branch tip — the same contract CI enforces.
Trade-off: Staleness caught minutes later than commit time.
Revisit trigger: Anchoring by content hash instead of commit SHA.

Date: 2026-07-15
Decision: LLM prose (`sync --prose`) is an injected callback that can only
          prepend prose above the scanned facts; failures degrade to plain sync.
Rationale: Keeps the §8 boundary mechanical — the model cannot alter facts,
          statuses, or scores by construction.
Trade-off: raw urllib, no SDK conveniences.
Revisit trigger: Prose grows beyond one paragraph per doc.
```

```
Date: 2026-07-21
Decision: Module dependency edges are tracked facts (Part C). The import graph
          `imports.py` computed only to propose watches is now a field on
          `RepoScan` (via `imports.compute_edges`, parsing reused not forked)
          and renders as a deterministic "Module boundaries (scanned)" section
          in the architecture auto-block. No new freshness code: a changed edge
          set regenerates the block, so `_claims_still_check_out` + the sync
          preview flag and heal it; each edge line is a Part B claim.
Rationale: The auto-block was a directory census that rarely changes, giving the
          freshness engine little semantic surface. Dependency edges are exactly
          the fact that moves when architecture shifts — but they were discarded,
          so a new cross-module import produced no signal (invisible drift).
Trade-off: Top-level-dir granularity only — shallow, resolver-free, no false
          precision (an intra-dir import is not an edge). Rendering sorts sources
          and targets so identical repo state is byte-identical across hash seeds
          — a flaky fact manufactures false stale, as corrosive as a false fresh.
Revisit trigger: Top-level-dir edges prove too coarse (want symbol-level edges),
          or a repo where the shallow regex import parse misleads.

Date: 2026-07-21
Decision: Trust resolves at the claim, not the doc (Part B). Evaluation yields a
          per-claim verdict (fresh/stale/unknowable) plus a conservative doc
          roll-up; the score's watch-quiet component becomes the fraction of
          claims that check out. New `claims.py` segments the human body into
          referencing units; `freshness` adds `ClaimVerdict`/`DocReport.claims`
          and line-diffs the generated facts; `verify`/`diffs`/`cli`/`ui`/`mcp`
          surface it. `--json` is additive only (VS Code + PR bot unchanged).
Rationale: One label per doc drags a solid doc amber for a single suspect
          sentence and never tells the AI *which* sentence to re-verify
          (product doc §1 pain #5). Part A already knows which symbol changed;
          Part B attributes it to the claim that references it.
Trade-off: The doc-level status stays the authoritative *whole-text* roll-up in
          `_claims_still_check_out` (not `all(claim fresh)`) so a claim the
          segmenter might miss can never sneak a doc to fresh — the breakdown is
          the finer view, the whole-text scan is the §10 safety net. Claim
          segmentation is deterministic markdown-block splitting, no parser.
Revisit trigger: A claim the segmenter drops that the whole-text roll-up
          catches (status stale, zero suspect claims shown); or a need to score
          generated vs human claims with different weights.

Date: 2026-07-21
Decision: Freshness resolves a changed watched file to the symbols it touched
          (Part A). `_claims_still_check_out` now clears a human claim about
          `module.symbol` only when that symbol's lines were provably untouched;
          a claim about a whole *path* still stales on any edit (unchanged).
          New: `symbols.py` (stdlib `ast` for Python, shallow regex for JS/TS,
          in the spirit of `imports.py`), `gitutil.changed_hunks` (new-side line
          ranges from `git diff --unified=0`, untracked files reported whole),
          `refs.extract_symbol_refs`. No frontmatter/schema change.
Rationale: Watch globs resolve at the file; claims live at the symbol. The old
          rule ignored `module.symbol` refs entirely — a body change to a
          described function was a silent false *fresh* (the path was never
          backticked and the coarse auto-block regenerates identically).
Trade-off: Symbol resolution may only *narrow* stale→fresh; any unparseable or
          ambiguous file (SyntaxError, deleted, non-Python/JS, unresolvable
          qualifier) falls back to path-level "assume stale" — never a false
          fresh (§10). Re-export aliases aren't followed (shallow, no resolver).
Revisit trigger: Any observed false fresh from symbol resolution; a real need
          to follow re-exports or to narrow the orphaned-anchor (digest) path.

Date: 2026-07-16
Decision: Agent integration = MCP stdio server + two-layer consent: editor prompts per call, .slate/agent-access is the read-default capability ceiling
Rationale: MCP is what coding agents already speak; a server-side ceiling caps the blast radius of an over-eager always-allow and is committable team policy
Trade-off: Two config surfaces to explain (editor allowlist + access file)
Revisit trigger: MCP framing churn, or read-default friction blocking adoption
```

```
Date: 2026-07-20
Decision: Freshness hardened against the two premortem failure modes: (1) stale
          requires proof of impact — if a fresh scan regenerates the identical
          auto-block and no human section references a changed path, the doc is
          fresh (content-verified), changed paths kept as evidence; (2) every
          stamp records slate_synced_digest (sha256 of watched files' content),
          and an orphaned commit anchor falls back to it — match = fresh,
          mismatch = stale, absent = needs-verification.
Rationale: (1) Broad watch globs flagged ~half of all commits; an always-yellow
          signal gets ignored and the sync ritual becomes noise. (2) Squash-merge
          (the GitHub default) orphaned every anchor, degrading the whole layer
          to a 0.25-capped rumor in every fresh clone and CI checkout.
Trade-off: status may run a repo scan when watched paths changed (still
          sub-second); digest mismatch can't enumerate committed paths.
Revisit trigger: Any observed false fresh from content verification; digest
          hashing felt (>1s) on large repos.
```

```
Date: 2026-07-24
Decision: Quantified-value surface — measured one-line receipts on every
          read/status/sync, a `slate value` cumulative ledger, and additive
          "value" fields on MCP slate_read/slate_sync. Ledger is clone-local
          (.git/slate/value.json), never committed, entirely outside trust math.
Rationale: The user should see what Slate saves on every run, not take it on
          faith — and a context-trust product cannot hallucinate its own
          marketing. The ledger stores measured events only (real file sizes,
          real runs, real wall-clock); token/dollar figures are display-time
          arithmetic under the same stated assumptions as benchmarks/benchmark.py.
          Catches dedupe per (doc, sync anchor); fresh-doc syncs record nothing
          avoided; small repos where the layer exceeds the baseline are reported
          as exactly that.
Trade-off: read/sync now run a freshness/scan pass for measurement (sub-second,
          local); one clone-local state file inside .git. Recording is
          best-effort by construction — a ledger failure never breaks a command.
Revisit trigger: Receipts reading as noise in the field, or evidence the
          exploration baseline misstates real agent behavior.
```
