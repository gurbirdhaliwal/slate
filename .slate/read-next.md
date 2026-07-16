---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 036eaa4
slate_synced_at: 2026-07-16T00:32:19+00:00
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

The 2026-07-15 pivot (hosted agent debugger → context control plane CLI)
just landed in the working tree and is **not yet committed**. Immediately
after committing it:

1. `slate sync` (re-anchors the generated docs to the pivot commit)
2. `slate mark read-next decisions`
3. commit the context updates — CI's `slate status --ci` gate needs this

Next up (product doc §11, Phase 2): PyPI release, pre-commit hook,
`slate diff`.

## Landmines

- `slate status` correctly shows generated docs as stale until the pivot
  commit + sync above happens. Don't "fix" that — it's the product working.
- Don't reintroduce the old `apps/`, `packages/`, `infra/` trees from git
  history; the pivot removed them deliberately (decision log 2026-07-15).
