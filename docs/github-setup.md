# GitHub environment setup (one-time, ~10 minutes)

The workflows in `.github/workflows/` implement local → dev → prod:

| Trigger | Workflow | Target |
|---|---|---|
| Pull request | `ci.yml` | build + test only (required checks) |
| Merge to `main` | `deploy-dev.yml` | dev stack, automatic |
| Publish release `v*` | `deploy-prod.yml` | prod, **pauses for human approval** |

The pipeline is only half the guarantee — the following repo settings are the
other half. Do this the day the repo is pushed to GitHub.

## 1. Ruleset on `main`

Settings → Rules → Rulesets → New branch ruleset:

- Target: include default branch (`main`), enforcement **Active**
- ✅ Require a pull request before merging
  - Required approvals: **0 while solo** (GitHub won't let you approve your own
    PR — 1 would deadlock you). Flip to **1 the day a peer joins.**
- ✅ Require status checks to pass — add `api`, `worker`, `dashboard`
  (the job names from `ci.yml`; they appear in the picker after the first PR run)
- ✅ Block force pushes
- ✅ Restrict deletions
- Do NOT add yourself to the bypass list — the point is that nobody, including
  admins, pushes to `main` directly.

## 2. Environments

Settings → Environments → New environment, twice:

**`dev`**
- Secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` → the **dev** stack
  (nano VPS, or the same box with a second compose project at `/opt/slate-dev`)
- No protection rules — merges to main should flow to dev unattended

**`production`**
- Secrets: same three names → the **prod** VPS (`/opt/slate`)
- ✅ Required reviewers: add yourself (and later, any peer)
- ✅ Deployment branches and tags → restrict to tags matching `v*`

Because secrets are environment-scoped, no workflow outside the gated
`production` job can ever read the prod SSH key.

## 3. Shipping to prod

```bash
# main is green and dev looks right:
gh release create v0.1.0 --generate-notes
# -> deploy-prod builds images tagged v0.1.0, then WAITS.
#    Approve it under Actions -> deploy-prod -> Review deployments.
```

Rollback: Actions → deploy-prod → select the previous release's run →
Re-run all jobs (images are version-tagged; data volumes survive deploys).

## 4. When a peer joins (checklist)

- Ruleset: required approvals 0 → 1
- `production` environment: decide who can approve prod deploys
- Optional: add a `CODEOWNERS` file so the localization engine, auth, and
  migrations (§13 hand-code list) always get a named reviewer
