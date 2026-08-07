---
slate_doc: read-next
slate_generated: false
slate_synced_commit: edd0c65e
slate_synced_at: 2026-08-02T18:35:32+00:00
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

Vary: Cookie is now conditional on session access, per the task contract in AGENTS.md:
- `flask.sessions.SecureCookieSession` already tracked `accessed`/`modified` via `__getitem__`/`get`/`setdefault`/`on_update`, and `SecureCookieSessionInterface.save_session` already gated `response.vary.add("Cookie")` on `session.accessed` (this was pre-existing, not new work this session).
- Added the missing piece: `flask.ctx.RequestContext._session`, a read-only property aliasing `self.session`, so internal/inspection code can look at the session (e.g. its `accessed`/`modified` flags) without that inspection being mistaken for the app reading session data.

Verified against `tests/` (not modified) with `PYTHONPATH=src python3 -m pytest tests/` — 475 passed, 2 pre-existing unrelated failures (missing `asgiref` async extra; a Werkzeug-version-dependent bad-Host-header test), 6 skipped.

## Landmines

The global environment's editable-installed `flask` package points at a *different* trial checkout (`../slate-fresh-hooked-1`), not this repo. Running plain `pytest` or `python3 -c "import flask"` from here silently tests the wrong source tree. Always force `PYTHONPATH=src` (or otherwise verify `flask.__file__` resolves under this repo) before trusting test results.
