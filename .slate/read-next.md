---
slate_doc: read-next
slate_generated: false
slate_synced_commit: b6e3bf1
slate_synced_at: 2026-07-16T17:05:17+00:00
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Agent integration (2026-07-16) is built on branch `phase-2-3` (PR #2): MCP server (`slate mcp`), `slate agent enable/access/status`, VS Code access toggle. This repo is wired (`.mcp.json`, `.cursor/mcp.json`) with access `full` — this very update was written through the MCP server. Next code work is Phase 4 (product doc §11).

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
