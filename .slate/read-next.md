---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 88a6b4a
slate_synced_at: 2026-07-16T00:52:14+00:00
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

The 2026-07-15 pivot (hosted agent debugger → context control plane CLI)
is committed and synced on branch `pivot-context-control-plane` (PR open
against main). Nothing else is in flight.

Next up (product doc §11, Phase 2): PyPI release, pre-commit hook,
`slate diff`.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and
  commit the doc updates in the same PR — CI's `slate status --ci` gate
  fails otherwise.
- Don't reintroduce the old `apps/`, `packages/`, `infra/` trees from git
  history; the pivot removed them deliberately (decision log 2026-07-15).
