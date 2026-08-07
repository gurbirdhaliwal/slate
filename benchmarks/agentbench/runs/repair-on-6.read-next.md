---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 29b6f26a
slate_synced_at: 2026-08-02T18:44:09+00:00
slate_synced_digest: 3973c8f65dbe9cde
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Just fixed: `Vary: Cookie` is now conditional on the session actually being read or modified during the request, per the contract in the task (accessed/modified tracked by SessionMixin; a session refresh alone — e.g. permanent + SESSION_REFRESH_EACH_REQUEST — no longer forces Vary).

Changes:
- `flask.ctx.RequestContext` now stores the session as `_session`, with a `session` property (getter/setter) for external compatibility (`flask.session` proxy, app.py, templating.py all still work unchanged).
- `flask.app.Flask.process_response` uses `ctx._session` directly.
- `flask.sessions.SecureCookieSessionInterface.save_session` snapshots `session.accessed` at the top of the method, before calling `should_set_cookie`/`get_expiration_time` (which read the `permanent` flag via `session.get()` and would otherwise pollute `accessed`). Both `Vary` additions now use that snapshot instead of unconditionally adding it after `set_cookie`.

Verified via manual test script and the full test suite (475 passed, 2 pre-existing unrelated failures: `test_async_view` needs the `async` extra installed, `test_bad_environ_raises_bad_request` is a werkzeug version mismatch — both present before this change too).

Nothing else in flight.

## Landmines

_None recorded._
