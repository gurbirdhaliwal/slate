---
slate_doc: read-next
slate_generated: false
slate_synced_commit: e5bc2d36
slate_synced_at: 2026-08-02T07:39:37+00:00
slate_synced_digest: 3ae648a6967a9bc8
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Conditional `Vary: Cookie` was already implemented in `flask.sessions` (accessed/modified tracking, header only added when the session was read/changed/refreshed). The remaining gap — exposing the session on the request context as `_session` for internal inspection — is now done: `flask.ctx.RequestContext` stores the session in `_session`, with a `session` property as the public passthrough. `Flask.process_response` (app.py) uses `ctx._session` directly for the null-session check and `save_session` call.

Nothing else in flight.

## Landmines

Don't confuse this with real upstream Flask: the `_session`/`session`-property split is specific to this repo, not present in pallets/flask proper. The two pytest failures (`test_async_view`, `test_bad_environ_raises_bad_request`) are pre-existing and unrelated to sessions — confirmed via `git stash` against HEAD before this change.
