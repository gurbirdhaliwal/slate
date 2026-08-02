---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 9cd9e26e
slate_synced_at: 2026-08-02T07:02:39+00:00
slate_synced_digest: c9700d60554a44e7
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Implemented conditional `Vary: Cookie` behavior for sessions (src/flask/sessions.py already had the accessed-gated logic in `save_session`). Added the missing piece: `RequestContext` now stores the session in `_session` (src/flask/ctx.py), with a `session` property kept for backward compatibility. `flask.session` (globals.py) and `app.py`'s `process_response` now source from `_session` directly. This lets code inspect `request_ctx._session.accessed`/`.modified` without the inspection itself counting as a session read. Full test suite passes except 2 pre-existing unrelated failures (missing async extra, werkzeug bad-Host-header status code mismatch) present before this change too.

## Landmines

Don't assume `Vary: Cookie` is unconditional — it's gated on `session.accessed` (set by SecureCookieSession.__getitem__/get/setdefault/on_update, not by mere attribute access or `ctx.session`/`ctx._session` retrieval). `tests/` must not be modified per task instructions.
