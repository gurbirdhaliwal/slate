---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 52e281a6
slate_synced_at: 2026-08-02T18:47:19+00:00
slate_synced_digest: 4be47c0e3701b573
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` holds the session on a plain `session` attribute, assigned once when the context is pushed. Reading it is an ordinary attribute access with no side effect. `RequestContext._session` is a read-only property returning that same object, for code that needs to inspect `accessed`/`modified` without it looking like a session read.

`flask.sessions.SessionMixin` records whether a session was changed, via `modified`. Nothing records whether it was merely read.

`flask.templating._default_template_ctx_processor` injects `request`, `session` and `g` into every template context.


_Nothing in flight._

## Landmines

_None recorded._
