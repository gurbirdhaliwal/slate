---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 50c6883e
slate_synced_at: 2026-08-01T18:07:30+00:00
slate_synced_digest: 56e17ba9ff3d97f9
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`flask.ctx.RequestContext` holds the session on a plain `session` attribute, assigned once when the context is pushed, and exposes it read-only as `_session` so it can be inspected (e.g. `.accessed`/`.modified`) without the inspection itself counting as a read.

`flask.sessions.SessionMixin` records whether a session was changed, via `modified`. Nothing records whether it was merely read.

`flask.templating._default_template_ctx_processor` injects `request`, `session` and `g` into every template context.


_Nothing in flight._

## Landmines

_None recorded._
