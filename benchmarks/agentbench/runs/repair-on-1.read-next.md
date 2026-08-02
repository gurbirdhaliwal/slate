---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 46b3f65e
slate_synced_at: 2026-08-02T18:12:31+00:00
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

Conditional `Vary: Cookie` is implemented end to end:

`flask.sessions.SecureCookieSession` tracks `accessed` (read or written) separately from `modified` (written). `__getitem__`, `get`, `setdefault`, and the `CallbackDict` `on_update` hook (fires on `__setitem__`/`__delitem__`/`clear`/etc.) all set `accessed = True`; merely opening/holding the session does not.

`flask.sessions.SecureCookieSessionInterface.save_session` only calls `response.vary.add("Cookie")` when `session.accessed` is true. It still unconditionally adds `Vary: Cookie` when it actually issues a `Set-Cookie` (new/refreshed/deleted cookie), since that response really does vary by cookie.

`flask.ctx.RequestContext` holds the session on a plain `session` attribute, assigned once when the context is pushed, plus a read-only `_session` property (added 2026-08-02, see [[decisions]]) that returns the same object — the documented way to inspect `accessed`/`modified` without that inspection itself counting as a read.

`flask.templating._default_template_ctx_processor` injects `request`, `session` and `g` into every template context.


_Nothing in flight._

## Landmines

_None recorded._
