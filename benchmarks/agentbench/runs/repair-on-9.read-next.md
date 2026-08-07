---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 08661832
slate_synced_at: 2026-08-02T18:56:38+00:00
slate_synced_digest: 7d88361b2a109575
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Implemented conditional `Vary: Cookie` for sessions.

- `flask.sessions.SecureCookieSession` already tracked `accessed`/`modified` (set on `__getitem__`, `get`, `setdefault`, and any mutation via `on_update`); `SecureCookieSessionInterface.save_session` already only adds `Vary: Cookie` when `session.accessed` (or on delete-cookie/set-cookie paths).
- What was missing: `flask.ctx.RequestContext` stored the session on a plain public `session` attribute. Renamed the storage to `RequestContext._session` (private) so internal code (`app.py` finalize_request, `templating.py` context processor, `ctx.py` copy/push) can inspect/pass around the session object without that inspection being mistaken for a read. The public `flask.session` proxy in `globals.py` now points `LocalProxy(_cv_request, "_session", ...)` — external behavior of `flask.session` is unchanged, only the internal attribute name moved.
- Verified: full test suite still 475 passed / 2 pre-existing unrelated failures (`test_async_view` needs `asgiref` extra not installed; `test_bad_environ_raises_bad_request` unrelated routing issue) — both failures present before this change too.

Nothing in flight.

## Landmines

Don't confuse the public `flask.session` proxy (unchanged name/behavior) with the internal `RequestContext._session` attribute (renamed from `session`). Any new internal code that needs the raw session object should use `ctx._session`, not `ctx.session` (no longer exists).
