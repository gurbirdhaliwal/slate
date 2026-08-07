---
slate_doc: read-next
slate_generated: false
slate_synced_commit: a95fbae8
slate_synced_at: 2026-08-01T18:30:12+00:00
slate_synced_digest: 4ce59543e16da888
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` now stores the session on a private `_session` attribute (set once when the context is pushed) with a read-only `session` property forwarding to it. Internal framework code (`Flask.finalize_request` in `app.py`) reads `ctx._session` directly so that framework bookkeeping never trips the session's own `accessed` flag.

`flask.sessions.SecureCookieSession` (in `sessions.py`) tracks `accessed`/`modified` itself by overriding `__getitem__`, `get`, `setdefault`, and the `on_update` callback passed to `CallbackDict`. `SessionInterface.should_set_cookie`/`get_expiration_time` read `session.permanent`, which goes through the tracked `get()` — this is intentional per the accessed contract (any key read counts), and doesn't affect the `Vary: Cookie` decision because `save_session` checks `session.accessed` before those calls run.

`SecureCookieSessionInterface.save_session` (sessions.py ~L360-399) adds `Vary: Cookie` in three independent cases: session was accessed/modified during the request, session was deleted, or the cookie was (re)written (covers `SESSION_REFRESH_EACH_REQUEST`). A request that never touches the session and doesn't trigger a cookie write gets no `Vary` header.

Verification note: the shared venv's editable Flask install points at a sibling trial checkout (`slate-fresh-hooked-1`), not this repo. Plain `python -m pytest` here silently tests the wrong source tree. Use `PYTHONPATH=src python -m pytest tests/` (or otherwise ensure `src/` is first on `sys.path`) to actually exercise this repo's code.

_Nothing in flight._

## Landmines

Running bare `pytest`/`python -m pytest` in this checkout can silently import Flask from a different trial's editable install (see venv note above) — always force `PYTHONPATH=src` (or verify `flask.__file__`) before trusting a local test run.
