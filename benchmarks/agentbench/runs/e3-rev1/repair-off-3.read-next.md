---
slate_doc: read-next
slate_generated: false
slate_synced_commit: b54ddaf9
slate_synced_at: 2026-08-01T18:46:47+00:00
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

`flask.ctx.RequestContext` now holds the session on `_session` (assigned once when the context is pushed, in `push()`/`__init__`/`copy()`). The public `flask.session` proxy (`flask.globals.session`) is a `LocalProxy` bound to the `_session` attribute name, not `session` — `RequestContext` no longer has a `session` attribute at all. Internal code that needs to inspect the session object without that inspection counting as a "read" (e.g. `Flask.process_response`'s `is_null_session`/`save_session` calls in app.py, and `_default_template_ctx_processor` in templating.py) reads `ctx._session` / `reqctx._session` directly.

`flask.sessions.SecureCookieSession` already tracked `accessed` (set in `__getitem__`, `get`, `setdefault`, and on any write via `on_update`) and `modified` (write-only, via `on_update`). `SecureCookieSessionInterface.save_session` already conditioned the `Vary: Cookie` header on `session.accessed` — this was true before this session's changes too, so the conditional-Vary behavior itself was not new; only the `_session` renaming/plumbing was added.

Nothing in flight.

## Landmines

Don't assume `RequestContext.session` exists — it was renamed to `_session`. `flask.globals.session` (the public proxy) forwards to the `_session` attribute now, so `LocalProxy(_cv_request, "_session", ...)` in globals.py must stay in sync with the attribute name in ctx.py.

When running tests/scripts in this trial's shell, `import flask` may resolve to site-packages editable-installed against a *different* trial directory (observed pointing at `slate-fresh-hooked-1`). Always prefix with `PYTHONPATH=src` (or otherwise force the local `src/flask`) before trusting test results — a bare `python -m pytest` can silently test the wrong repo's code.
