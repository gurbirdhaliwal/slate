---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 79372da
slate_synced_at: 2026-07-16T01:35:57+00:00
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Phases 1–3 are implemented, committed, and synced on branch
`pivot-context-control-plane` (PR #1 against main). Nothing is in flight;
next code work is Phase 4 (team dashboard, merge policies, hosted bot —
product doc §11).

Remaining one-time owner tasks (not code): create the `slate-context`
project + trusted publisher on pypi.org, then tag `v0.2.0` after PR #1
merges; optionally publish the VS Code extension to the marketplace.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and
  commit the doc updates in the same PR — CI's `slate status --ci` gate
  fails otherwise.
- Don't reintroduce the old `apps/`, `packages/`, `infra/` trees from git
  history; the pivot removed them deliberately (decision log 2026-07-15).
