---
slate_doc: read-next
slate_generated: false
slate_synced_commit: a1e8db6
slate_synced_at: 2026-07-21T22:21:57+00:00
slate_synced_digest: e3b0c44298fc1c14
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

**Part A — symbol-level change detection — landed (2026-07-21).** The freshness
engine now resolves a changed watched file to the *symbols* it touched, so a
human claim about `context.get_auto_block` only stales when that function's
lines actually move — not when a docstring two functions over changes. New
`slate/symbols.py` (stdlib `ast` for Python, shallow regex for JS/TS),
`gitutil.changed_hunks` (per-file new-side line ranges from `git diff
--unified=0`), and `refs.extract_symbol_refs` (backticked `module.symbol`).
The rewire lives in `freshness._claims_still_check_out`; symbol resolution may
only ever *narrow* stale→fresh, and any unparseable/ambiguous file falls back
to path-level "assume stale". See the decision log entry dated 2026-07-21.

**Part B — claim-level trust — landed (2026-07-21).** Evaluation now yields a
per-claim verdict (fresh/stale/unknowable) plus a conservative doc roll-up, so
`slate status` reads "2 of 5 claims suspect" and names the sentence. New
`slate/claims.py` segments the human body into referencing units (its walk is
*total* — the union of a doc's claim refs equals its whole-text refs, so nothing
the trust path relies on is dropped); `freshness` adds `ClaimVerdict` +
`DocReport.claims`, reuses Part A's `_symbol_verdict`, and line-diffs the
generated facts. `verify` watch-quiet is now the fraction of claims that check
out. The doc-level status stays the authoritative whole-text roll-up in
`_claims_still_check_out` (never a false fresh); the breakdown is the finer view.
`--json` is additive (status/verify/diff gained claim fields; MCP mirrors them).

**Part C — dependency edges as tracked facts — landed (2026-07-21).** The
module-level import graph `imports.py` used only to suggest watches is now a
field on `RepoScan` (`scanner` computes it via `imports.compute_edges`, parsing
reused not forked) and renders as a deterministic "Module boundaries (scanned)"
section in the architecture auto-block. Crossing a module boundary now
regenerates the block differently, so the existing freshness/sync machinery
flags and heals it with no new trust code; each edge line is a Part B claim.
Rendering sorts sources and targets (byte-identical across `PYTHONHASHSEED`),
top-level-dir granularity only — no resolver, no false precision.

**The precision-upgrade arc (A→B→C) is complete.** File→symbol→claim resolution
plus dependency-edge facts. Remaining carry-overs, both optional refinements
(not blockers): (1) the orphaned-anchor path is digest-gated (no baseline to
diff) — a safe narrowing compares the recorded digest against the digest *at
HEAD*, then resolves working-tree changes by symbol; (2) shallow resolution
treats `module.symbol` as living in `module` — re-export aliases aren't followed
(accepted bound, matches `imports.py`). A natural next arc is symbol-level edges
(which *symbol* imports which), but only if top-level-dir granularity proves too
coarse in practice.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
