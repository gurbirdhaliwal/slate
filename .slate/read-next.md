---
slate_doc: read-next
slate_generated: false
slate_synced_commit: a196b0e
slate_synced_at: 2026-07-21T22:09:14+00:00
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

**Next: Part C — dependency-edge facts.** Part B knows which claim a change
touched; Part C should record *edges* (this doc's claim depends on that
module/symbol) so a change to a dependency can flag dependents that don't
textually reference it. Carry-over follow-ups still open: (1) the orphaned-anchor
path is digest-gated (no baseline to diff) — a safe refinement compares the
recorded digest against the digest *at HEAD*, then resolves working-tree changes
by symbol; (2) shallow resolution treats `module.symbol` as living in `module` —
re-export aliases aren't followed (accepted bound, matches `imports.py`).

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
