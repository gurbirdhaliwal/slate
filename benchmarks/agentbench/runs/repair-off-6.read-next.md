---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 27be9338
slate_synced_at: 2026-08-02T19:24:09+00:00
slate_synced_digest: f7c6f9db02fdcfc4
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` holds the session on a `_session` attribute (renamed from `session`), assigned once when the context is pushed. Reading it is an ordinary attribute access with no side effect — internal code (app.py's finalize_request, templating.py's context processor, globals.py's `flask.session` proxy) reads `ctx._session` so that merely obtaining a reference is never conflated with actually reading a key.

`flask.sessions.SecureCookieSession` records both `modified` (key written) and `accessed` (key read or written) — see `__getitem__`/`get`/`setdefault`/`on_update` in `src/flask/sessions.py`. `SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when `session.accessed` is true, or once it actually calls `response.set_cookie`/`delete_cookie` for that request.

`flask.templating._default_template_ctx_processor` injects `request`, `session` (from `reqctx._session`) and `g` into every template context.


_Nothing in flight._

## Landmines

_None recorded._
