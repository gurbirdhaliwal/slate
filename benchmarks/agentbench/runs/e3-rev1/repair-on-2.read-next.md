---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 97fce39d
slate_synced_at: 2026-08-01T18:12:56+00:00
slate_synced_digest: 176bfd327e9f889a
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` stores the session on `_session`, assigned once when the context is pushed. `session` is now a property delegating to `_session`, so internal code can read `_session` directly without it being mistaken for a view accessing the session.

`flask.sessions.SessionMixin` records whether a session was changed, via `modified`. Nothing records whether it was merely read.

`flask.templating._default_template_ctx_processor` injects `request`, `session` and `g` into every template context.


_Nothing in flight._

## Landmines

_None recorded._
