---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 13da8802
slate_synced_at: 2026-08-02T18:52:49+00:00
slate_synced_digest: 3ac7fc79b2e068b3
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Conditional `Vary: Cookie` on session access is implemented and working (`flask.sessions.SecureCookieSession.accessed`/`modified`, checked in `SecureCookieSessionInterface.save_session`). This session's change: `flask.ctx.RequestContext` now stores the session in `_session`, with `session` as a property over it, so the raw object can be inspected (e.g. in tests/tooling) without that inspection counting as a session read. All existing `ctx.session` / `flask.session` call sites are unaffected.

Full test suite passes except two pre-existing, unrelated failures: `TestStreaming::test_async_view` (missing `asgiref`/async extra) and `test_bad_environ_raises_bad_request` (Werkzeug status-code mismatch on malformed Host header).

## Landmines

Running bare `pytest` (or `python3 -c "import flask"`) in this checkout can silently import Flask from a *different* trial's editable install in the shared venv (seen resolving to `../slate-fresh-hooked-1/src/flask`) instead of this repo's `src/flask`. Always run tests with `PYTHONPATH=src` (or verify `flask.__file__`) to be sure you're testing the code you actually edited.
