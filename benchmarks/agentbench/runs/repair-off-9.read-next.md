---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 27be9338
slate_synced_at: 2026-08-02T19:38:24+00:00
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

Conditional `Vary: Cookie` is implemented: `flask.sessions.SecureCookieSession` tracks both `accessed` (read or written) and `modified` (written) independently, and `SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when `accessed` is true. Merely opening a request no longer marks the session accessed.

`flask.ctx.RequestContext` now holds the session on `_session` (renamed from the previously public-looking `session`), so internal code (`save_session`, the template context processor) can inspect the object by reference without that inspection counting as a read. `flask.session` (the public `LocalProxy`) is unaffected — it proxies to the `_session` attribute name.

`flask.templating._default_template_ctx_processor` injects `request`, `session` (from `reqctx._session`) and `g` into every template context.

_Nothing in flight._

## Landmines

_None recorded._
