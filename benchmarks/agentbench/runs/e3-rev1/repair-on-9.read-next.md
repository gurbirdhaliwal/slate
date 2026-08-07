---
slate_doc: read-next
slate_generated: false
slate_synced_commit: ecced5fc
slate_synced_at: 2026-08-02T08:11:09+00:00
slate_synced_digest: f50b1ed9d8522678
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

`_session`/`session` split landed in `flask.ctx.RequestContext`: `_session` is the real storage, `session` is a property delegating to it. `app.py`'s `full_dispatch_request` now inspects `ctx._session` when calling into `save_session`, so framework-side inspection is explicit about not being a "read." `sessions.py`'s `accessed`/`modified` tracking (and the conditional `Vary: Cookie` in `SecureCookieSessionInterface.save_session`) was already correct going into this task — no change needed there.

_Nothing in flight._

## Landmines

_None recorded._
