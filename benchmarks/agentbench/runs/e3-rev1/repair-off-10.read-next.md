---
slate_doc: read-next
slate_generated: false
slate_synced_commit: dcb4fd83
slate_synced_at: 2026-08-02T07:23:06+00:00
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

Just implemented conditional `Vary: Cookie` for sessions (AGENTS.md task): a response now gets `Vary: Cookie` only if the session was read or changed during the request, not merely because a request handled a session cookie. Changes: `SessionMixin.accessed` default now `False` and is no longer set by `SecureCookieSession.__getitem__/get/setdefault` (those overrides were removed); `RequestContext` renamed its `session` attribute to `_session` and added a `session` property that sets `accessed=True` on access — this is the single tracking point now, used by the `flask.session` proxy, templates (via the pre-registered Jinja global, not the per-request context processor), and app.py's dispatch. `RequestContext._session` is the untracked raw session object for internal framework checks (e.g. `is_null_session`) that shouldn't count as a read. Verified with tests/ (475 passed, same 2 pre-existing unrelated failures: missing asgiref/async extra, and an unrelated bad-Host-header 404-vs-400 test) plus a manual repro showing a no-touch request gets no Vary header even with an existing session cookie. Not yet committed.

## Landmines

Don't re-add accessed=True inside SecureCookieSession's dict methods — that was the old (broken) design and reintroducing it duplicates/bypasses the new RequestContext-level tracking. Internal code (should_set_cookie, get_expiration_time, is_null_session) intentionally reads the raw `_session` object, not the tracked `session` property, to avoid marking accessed as a side effect.
