---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 75ff0534
slate_synced_at: 2026-08-01T18:40:54+00:00
slate_synced_digest: 679a84bf0d09633c
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Conditional `Vary: Cookie` is implemented (restored to match upstream Flask 3.1.3): `flask.ctx.RequestContext` stores the session on `_session`; the public `session` property sets `SessionMixin.accessed = True` on access, so obtaining the session (e.g. via the `flask.session` proxy, including a mere key read) is what marks it read. `SecureCookieSession` no longer overrides `__getitem__`/`get`/`setdefault` for this — tracking lives on the request-context property, not the dict.

`flask.sessions.SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when `session.accessed` or `session.modified` is set, so a request that never touches the session doesn't get the header.

`flask.templating._default_template_ctx_processor` deliberately does **not** inject a concrete `session` object into the template context (that would mark every rendered request as accessed). Templates still see `session` via the global proxy, which lazily triggers the `RequestContext.session` property only if actually used.

`app.py process_response` reads `ctx._session` directly (bypassing the `session` property) so checking `is_null_session`/calling `save_session` doesn't itself mark the session accessed.

_Nothing in flight._

## Landmines

_None recorded._
