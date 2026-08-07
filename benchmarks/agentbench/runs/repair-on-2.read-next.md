---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 5b647ec9
slate_synced_at: 2026-08-02T18:18:46+00:00
slate_synced_digest: 3147a387faf9ecf4
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`Vary: Cookie` is conditional: `SecureCookieSessionInterface.save_session` only adds it when `session.accessed` or `session.modified` is true, or when the cookie actually gets (re)written (`src/flask/sessions.py`). `SecureCookieSession.accessed` is flipped by `__getitem__`, `get`, `setdefault`, and any mutation (via `CallbackDict`'s `on_update`) — not by merely handling a request.

`flask.ctx.RequestContext` holds the session on `self._session` (not `session`). The `flask.session` proxy (`globals.py`) resolves to `ctx._session` via `LocalProxy`. Internals that need to peek at the session (e.g. `flask.templating._default_template_ctx_processor`, `Flask.save_session`) read `ctx._session` directly so that the peek itself never flips `accessed`.

_Nothing in flight._

## Landmines

_None recorded._
