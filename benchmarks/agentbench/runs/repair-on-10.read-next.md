---
slate_doc: read-next
slate_generated: false
slate_synced_commit: c4d9e6de
slate_synced_at: 2026-08-02T19:02:09+00:00
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

`flask.ctx.RequestContext` holds the session on a private `_session` attribute, assigned once when the context is pushed. Reading it is an ordinary attribute access with no side effect; the `flask.session` proxy and internal callers (`flask.app.Flask.finalize_request`, `flask.templating._default_template_ctx_processor`) access it via `_session`.

`flask.sessions.SessionMixin` records whether a session was changed, via `modified`. Nothing records whether it was merely read.

`flask.templating._default_template_ctx_processor` injects `request`, `session` and `g` into every template context, reading the session via `flask.ctx.RequestContext._session` — the injection itself does not mark the session as accessed, only actual use of `session` inside a template does.


_Nothing in flight._

## Landmines

_None recorded._
