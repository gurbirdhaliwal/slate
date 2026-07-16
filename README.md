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

slate diff          # what changed vs. what each doc claims + sync preview
slate sync          # regenerate the auto-blocks, re-anchor to HEAD
slate verify        # 0.00–1.00 trust score per doc
slate read          # the ordered "first read" path for an AI session
```

Beyond the core loop:

```bash
slate sync --prose      # opt-in: LLM-drafted orientation paragraph above the
                        # scanned facts (needs ANTHROPIC_API_KEY; the facts and
                        # all trust math stay deterministic)
slate watches --apply   # propose watch globs from import graphs + doc references
slate hook install      # pre-push gate: refuses to push a stale context layer
slate fleet ~/code      # freshness roll-up across many repos
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

## Wire it into your coding agent (MCP)

Slate ships an MCP server so your AI agent runs Slate itself — no more
manually running commands and pasting output into the chat:

```bash
slate agent enable claude     # Claude Code (.mcp.json) — or: cursor, all
slate agent access full       # optional: let the agent maintain the layer too
```

Restart the agent session; it now has these tools:

| Tool | Access | What the agent does with it |
|------|--------|------------------------------|
| `slate_read` | read | session start: the ordered context set with trust labels + scores |
| `slate_status` / `slate_verify` / `slate_diff` | read | mid-task: is this doc still safe? what exactly broke? |
| `slate_sync` | full | session end: regenerate auto-blocks, re-anchor freshness |
| `slate_update_focus` | full | session end: rewrite read-next's "Current focus" for the next session |
| `slate_mark` / `slate_append_decision` | full | attest human docs / record decisions worth keeping |

**Consent works in two layers, Claude Code-style.** Your editor prompts per
tool call (until you always-allow a tool there). Underneath, Slate's own
access mode is the hard ceiling: it defaults to **read-only** — the mutating
tools aren't even exposed — and `slate agent access full` (or the
"Slate: Agent Access" command in VS Code) unlocks them. The mode lives in
`.slate/agent-access`, so committing it makes it team policy, and toggling
it takes effect without restarting the agent.

## Integrations

- **GitHub PR bot** — [action.yml](action.yml) is a reusable composite action:
  it checks the consumer repo's context layer on every PR and posts (and
  edits in place) a comment listing which docs the PR invalidates, with
  trust scores. Two lines in a consumer workflow:
  `uses: gurbirdhaliwal/slate@v0.2.0` after a `fetch-depth: 0` checkout.
- **VS Code extension** — [integrations/vscode/](integrations/vscode/):
  trust badges in the file tree, a status-bar roll-up, and one-click sync.
  Plain JS, no build step; renders `slate status --json`, never computes.
- **pre-commit framework** — [.pre-commit-hooks.yaml](.pre-commit-hooks.yaml)
  (`id: slate-context`, runs at pre-push); or `slate hook install` for the
  same gate without the framework.
- **PyPI releases** — pushing a `v*` tag builds and publishes via
  [release.yml](.github/workflows/release.yml) (PyPI trusted publishing;
  one-time project setup on pypi.org required).

## Repository layout

```
slate/                the CLI package (stdlib only, by design)
├── cli.py            argparse entry point (all commands, --json contracts)
├── scanner.py        deterministic repo scan (languages, modules, commands)
├── generator.py      scan -> Markdown context layer, auto-block rewriting
├── freshness.py      the freshness engine: fresh / stale / needs-verification
├── verify.py         verification score (reference validity + watch quiet + drift)
├── diffs.py          slate diff: change kinds, broken claims, sync preview
├── imports.py        watch inference from import graphs + doc references
├── llm.py            opt-in prose writer (urllib, injectable transport)
├── hooks.py          pre-push freshness gate installer
├── context.py        doc registry, frontmatter stamping, auto-block markers
├── frontmatter.py    tiny hand-rolled YAML-subset frontmatter (no deps)
├── globs.py          watch-pattern matching with ** semantics
└── gitutil.py        git plumbing (change detection anchors)
integrations/
├── github/           PR bot script used by the root action.yml
└── vscode/           editor extension (plain JS, no build step)
tests/                pytest suite — runs against real throwaway git repos
.github/workflows/    ci.yml (tests + dogfood + PR bot) · release.yml (PyPI)
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

## Current state (Phases 1–3 built)

Working end to end: `init` → generated context layer with freshness
frontmatter → `status`/`verify`/`read`/`diff` → `sync`/`mark`, plus the
pre-push hook, watch inference, opt-in LLM prose, the PR bot action, the
VS Code extension, and `fleet`. Dogfooded on this repo (see
[AGENTS.md](AGENTS.md) and [.slate/](.slate/)); CI runs the tests, the
freshness gate, and the PR bot.

Remaining one-time setup (needs account owner): create the `slate-context`
project + trusted publisher on pypi.org, then push a `v0.2.0` tag; publish
the VS Code extension to the marketplace if wanted (works from a local VSIX
today). Phase 4 (team dashboards, merge policies, hosted bot) is not built.
