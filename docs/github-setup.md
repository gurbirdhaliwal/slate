# GitHub repo setup (one-time, ~5 minutes)

> **Current status (2026-07-14, still true after the 2026-07-15 pivot):** repo
> created (`gurbirdhaliwal/slate`, private), CI green. **Enforcement is NOT
> active:** rulesets need GitHub Pro on private repos, and we're on Free for
> now. Direct pushes to main are technically possible. See "Activating
> enforcement" below for the command to run after upgrading.
>
> **2026-07-15 pivot note:** Slate is now a repo-local CLI — there is no
> deploy target anymore. The `dev`/`production` GitHub Environments and the
> deploy workflows were removed with the pivot; "shipping" is publishing to
> PyPI (Phase 2 of the build plan). Only the branch protection matters now.

The single workflow in `.github/workflows/`:

| Trigger | Workflow | What it gates |
|---|---|---|
| Pull request / push to `main` | `ci.yml` (job: `tests`) | pytest suite + `slate status --ci` dogfood check |

## 1. Ruleset on `main`

Settings → Rules → Rulesets → New branch ruleset:

- Target: include default branch (`main`), enforcement **Active**
- ✅ Require a pull request before merging
  - Required approvals: **0 while solo** (GitHub won't let you approve your own
    PR — 1 would deadlock you). Flip to **1 the day a peer joins.**
- ✅ Require status checks to pass — add `tests`
  (the job name from `ci.yml`; appears in the picker after the first PR run)
- ✅ Block force pushes
- ✅ Restrict deletions
- Do NOT add yourself to the bypass list — the point is that nobody, including
  admins, pushes to `main` directly.

## Activating enforcement (after upgrading to GitHub Pro)

The ruleset is checked in at `.github/rulesets/protect-main.json`:

```bash
gh api -X POST repos/gurbirdhaliwal/slate/rulesets \
  --input .github/rulesets/protect-main.json
```

Until then: treat "no direct pushes to main" as team discipline — always
branch, always PR, even solo.

## 2. When a peer joins (checklist)

- Ruleset: required approvals 0 → 1
- Optional: add a `CODEOWNERS` file so the freshness engine and verification
  scoring (the hand-code list, product doc §10) always get a named reviewer
