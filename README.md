# Slate — Context Control Plane for AI-Assisted Repos

Slate keeps AI and humans aligned with the current state of a codebase. It
generates a small set of concise Markdown context files beside the code,
detects which of them a code change may have invalidated, and surfaces what
is **safe to trust** before the next AI action — so every session starts
from reality instead of guesswork.

The single source of truth for product and architecture decisions is
[slate-product-doc.md](slate-product-doc.md) — read §3 (wedge), §7 (context
layer design), and §10 (build vs vibecode rules) before touching anything.

## How it works

```bash
cd your-repo
slate init          # scan the repo, generate the context layer
git add -A && git commit -m "add context layer"

# ... code changes land ...

slate status        # which context docs are now suspect?
○ .slate/modules.md        stale   2 watched path(s) changed since 3f2c91a
    ↳ src/billing/tax.py

slate sync          # regenerate the auto-blocks, re-anchor to HEAD
slate verify        # 0.00–1.00 trust score per doc
slate read          # the ordered "first read" path for an AI session
```

Every context doc carries freshness metadata (sync anchor commit + watch
globs) in its frontmatter and is always in one of three states:

| Status | Meaning |
|--------|---------|
| `fresh` | no watched code changed since the doc was synced — safe to rely on |
| `stale` | watched code changed (committed *or* uncommitted) — verify before acting |
| `needs-verification` | the freshness anchor is gone (rebase/squash/hand-edit) — treat as a rumor |

## What it generates

```
AGENTS.md                 routing + trust protocol at the repo root (read first)
.slate/read-next.md       current focus — the smallest useful context for the task at hand
.slate/architecture.md    what the system is and its invariants
.slate/modules.md         where things live (scanned module map)
.slate/workflows.md       how to build, test, run (scanned commands)
.slate/decisions.md       why things are the way they are (append-only log)
```

Generated docs contain a marked auto-block that `slate sync` rewrites from a
deterministic repo scan; everything outside the block is human-owned and
survives every sync. `read-next.md` and `decisions.md` are fully human-owned —
Slate only tracks their freshness (`slate mark` attests them).

## Install

```bash
pip install -e .          # Python ≥ 3.11, zero runtime dependencies
slate --version
```

Requires a git repository — Slate anchors freshness to git history.

## Repository layout

```
slate/                the CLI package (stdlib only, by design)
├── cli.py            argparse entry point: init/status/sync/mark/verify/read
├── scanner.py        deterministic repo scan (languages, modules, commands)
├── generator.py      scan -> Markdown context layer, auto-block rewriting
├── freshness.py      the freshness engine: fresh / stale / needs-verification
├── verify.py         verification score (reference validity + watch quiet + drift)
├── context.py        doc registry, frontmatter stamping, auto-block markers
├── frontmatter.py    tiny hand-rolled YAML-subset frontmatter (no deps)
├── globs.py          watch-pattern matching with ** semantics
└── gitutil.py        git plumbing (change detection anchors)
tests/                pytest suite — runs against real throwaway git repos
.github/workflows/    ci.yml: pytest + `slate status --ci` dogfood gate
docs/github-setup.md  one-time repo config (branch ruleset)
```

## Development

```bash
make install    # venv + editable install with dev deps
make test       # pytest (31 tests, real git repos in tmpdirs)
make demo       # throwaway repo walking the core loop end to end
make dogfood    # slate status on this repo's own context layer
```

## Verifying a change

- `make test` — the freshness engine and verification scoring are the
  hand-code-carefully core (§10); both are covered by tests that build real
  git repos.
- `make demo` — eyeball the actual CLI output on a fresh repo.
- CI also runs `slate status --ci` against this repo's own context layer:
  if your change touches watched code, run `slate sync` and commit the doc
  updates with it.

## The rules that matter (§10)

Hand-code (a false "fresh" destroys the product's promise): the freshness
derivation, watch-glob matching, git change detection, verification scoring,
frontmatter round-tripping, and the auto-block boundary logic. **Vibecode
freely:** doc templates, CLI presentation, scanner heuristics for new
languages/build tools.

## Current state (MVP)

Working end to end: `init` → generated context layer with freshness
frontmatter → `status`/`verify`/`read` → `sync`/`mark`. Dogfooded on this
repo (see [AGENTS.md](AGENTS.md) and [.slate/](.slate/)).

Not yet built (phased, see §11): LLM-assisted prose updates on sync, watch
inference from imports, `slate diff` (what changed vs. what the doc claims),
pre-commit hook, PyPI release, IDE/PR-bot integrations.
