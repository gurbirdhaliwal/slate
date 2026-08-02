---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 08019fad
slate_synced_at: 2026-08-02T19:38:11+00:00
slate_synced_digest: 2f1a5dcaf1acb14c
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Conditional `Vary: Cookie` for sessions is implemented. `SecureCookieSession` tracks `accessed`/`modified`; `SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when `session.accessed` is true (or when the cookie is actually set/deleted). `RequestContext` now stores the session on `_session` and exposes a read-only `session` property forwarding to it, so internal code (e.g. `Flask.finalize_request` in app.py) can reference the raw session via `ctx._session` without going through any read-tracked accessor.

`flask.templating._default_template_ctx_processor` still injects `request`, `session` and `g` into every template context (unchanged, reads `reqctx.session`).

Nothing in flight.

## Landmines

`RequestContext.session` is a read-only property now (backed by `_session`) — don't reassign `ctx.session` directly, use `ctx._session`.
