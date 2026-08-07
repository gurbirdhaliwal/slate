---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 76d098e2
slate_synced_at: 2026-08-02T07:34:37+00:00
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

`flask.ctx.RequestContext` now stores the session on `_session` (not `session`), assigned once when the context is pushed. `flask.globals.session` (the public `flask.session` proxy) forwards to `_session` via LocalProxy. Internal readers (`Flask.finalize_request` in app.py, `_default_template_ctx_processor` in templating.py) use `ctx._session` / `reqctx._session` directly.

`flask.sessions.SessionMixin` records both `modified` (written) and `accessed` (read or written) — `SecureCookieSession` sets `accessed` in `__getitem__`, `get`, `setdefault`, and its `on_update` callback. `SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when `session.accessed` is true, or when it actually writes/deletes the session cookie (modified, or permanent refresh). A request that never reads or writes the session gets no `Vary: Cookie`.

Note: the shared venv's editable Flask install may point at a sibling trial directory rather than this repo — run tests with `PYTHONPATH=src` to force local source (verify with `python -c "import flask; print(flask.__file__)"` first).

_Nothing in flight._

## Landmines

The shared `.venv`'s editable Flask install can silently resolve to a *different* trial's `src/flask`, so `pytest`/`python -c "import flask"` without `PYTHONPATH=src` will test the wrong code and give a false pass. Always confirm `flask.__file__` points into this repo before trusting test results.
