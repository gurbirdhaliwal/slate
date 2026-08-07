---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 43eded81
slate_synced_at: 2026-08-02T08:16:21+00:00
slate_synced_digest: 311458c1e382f4bd
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` now holds the session on `_session`, assigned once when the context is pushed. `flask.session` (globals.py) and internal callers (app.py `process_response`, templating.py context processor, `RequestContext.copy`) all read `_session`.

`flask.sessions.SecureCookieSession` tracks both `modified` (any write) and `accessed` (any read via `__getitem__`/`get`/`setdefault`, or any write via `on_update`) — this was already correct prior to this session's change.

`SecureCookieSessionInterface.save_session` adds `Vary: Cookie` only when `session.accessed` is true, so requests that never touch the session get no `Vary: Cookie` header. Verified with a manual smoke test and `tests/test_basic.py::test_session_vary_cookie` / `test_session_refresh_vary`.

Nothing in flight.

## Landmines

The venv at Slate/.venv has an editable Flask install pointing at a different trial directory (slate-fresh-hooked-1), so running plain `pytest` without `PYTHONPATH=$(pwd)/src` silently tests the wrong source tree. Always set `PYTHONPATH` to this repo's `src` when running tests here.

Two pre-existing, unrelated test failures in this environment: `tests/test_helpers.py::TestStreaming::test_async_view` (missing `asgiref` extra) and `tests/test_reqctx.py::test_bad_environ_raises_bad_request` (werkzeug version behavior difference). Both fail on a clean checkout too.
