---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 49269dc0
slate_synced_at: 2026-08-02T07:27:36+00:00
slate_synced_digest: eba6e6b7a991adf8
slate_watches:
  - examples/**
  - src/**
  - tests/**
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

Session `Vary: Cookie` conditionality is implemented and verified: `SecureCookieSession` tracks `accessed`/`modified` (src/flask/sessions.py), and `SecureCookieSessionInterface.save_session` only adds `Vary: Cookie` when the session was accessed, modified, or the cookie is actually (re)written — a request that never touches the session gets no `Vary` header.

`flask.ctx.RequestContext` now stores the session on `self._session`, with a `session` property (getter/setter) forwarding to it. Internal call sites that only need to inspect the session for bookkeeping (`RequestContext.push`/`copy`, `Flask.finalize_request`'s save-session check) read `ctx._session` directly so that inspection is never mistaken for the request reading the session. `flask.session` (the public proxy) and user code still go through the `session` property/attribute as before.

`flask.templating._default_template_ctx_processor` still injects `request`, `session` and `g` into every template context via the `session` property — unchanged.

Verified against HEAD by reading src/flask/sessions.py and src/flask/ctx.py directly and running the test suite (PYTHONPATH=src, since the shared venv's editable Flask install points at a different trial checkout).

## Landmines

The shared .venv has Flask installed editable pointing at .work/trials/slate-fresh-hooked-1, NOT this checkout. Running plain `pytest` here silently tests the wrong source tree — always run with `PYTHONPATH=src` (or reinstall editable) from this repo root to test local changes.

tests/test_helpers.py::TestStreaming::test_async_view and tests/test_reqctx.py::test_bad_environ_raises_bad_request fail in this environment regardless of session changes (missing 'async' extra; werkzeug host-validation behavior mismatch). Not related to session/Vary work — pre-existing environment issues.
