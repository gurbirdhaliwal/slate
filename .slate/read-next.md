---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 6f28164
slate_synced_at: 2026-07-21T18:55:35+00:00
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

**Next: Part B — claim-level attribution.** Part A resolves at the symbol; Part
B should attribute *which sentence/claim* a changed symbol invalidates (today a
whole doc goes stale) and lay in dependency-edge facts. Two known follow-ups
surfaced by Part A: (1) the orphaned-anchor path is still digest-gated — it
can't narrow because it has no baseline to diff; a safe refinement is to
compare `slate_synced_digest` against the digest *at HEAD* and, on a match,
resolve the remaining working-tree changes by symbol; (2) shallow resolution
treats `module.symbol` as living in `module` — a re-export alias can't be
followed (accepted bound, matches `imports.py`'s no-resolver philosophy).

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
