---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 5aac6d5
slate_synced_at: 2026-07-16T01:35:13+00:00
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Phases 2 and 3 are implemented in the working tree (branch
`pivot-context-control-plane`, PR #1) and **not yet committed**: `slate
diff`, `slate watches`, `slate hook` (pre-push), `slate sync --prose`,
`slate fleet`, the PR-bot composite action (`action.yml`), the VS Code
extension (`integrations/vscode/`), release automation, and
pre-commit-framework support. After committing: `slate sync`, then
`slate mark read-next decisions`, then commit the doc updates.

Remaining one-time owner tasks (not code): create the `slate-context`
project + trusted publisher on pypi.org, then tag `v0.2.0`; optionally
publish the VS Code extension to the marketplace.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and
  commit the doc updates in the same PR — CI's `slate status --ci` gate
  fails otherwise.
- Don't reintroduce the old `apps/`, `packages/`, `infra/` trees from git
  history; the pivot removed them deliberately (decision log 2026-07-15).
