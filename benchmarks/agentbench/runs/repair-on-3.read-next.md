---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 33ec2bab
slate_synced_at: 2026-08-01T18:18:52+00:00
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

`flask.ctx.RequestContext` holds the raw session on `_session`, assigned when the context is pushed. `session` is now a property (backing the `flask.session` proxy) that sets `accessed = True` as a side effect of being read — use `_session` internally when inspection shouldn't count as access.

`flask.sessions.SessionMixin` records both whether a session was changed (`modified`) and whether it was merely read (`accessed`). `accessed` now defaults to `False` and is set by `flask.ctx.RequestContext.session`, not by `SecureCookieSession`'s dict methods.

`flask.templating._default_template_ctx_processor` injects `request` and `g` into every template context; `session` is left for the `flask.session` proxy to resolve lazily, since reading it must go through `RequestContext.session` to mark `accessed`.


_Nothing in flight._

## Landmines

`tests/test_basic.py::test_session` asserts `flask.session.accessed` is `False` before any key is read inside a view. That assumption no longer holds: reading the `flask.session` proxy at all now goes through `RequestContext.session`, which sets `accessed = True` as a side effect (this is what lets `in`/`len` checks also mark the session as read, closing a cache-poisoning gap). The test predates the fix and was intentionally left unmodified per task constraints — expect it to fail until it's replaced with something like upstream's `test_session_accessed`, which asserts against `request_ctx._session.accessed` instead of the proxy.
