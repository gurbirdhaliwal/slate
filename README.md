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
slate merge install     # git merge driver: concurrent PRs stop colliding (teams)
slate fleet ~/code      # freshness roll-up across many repos
slate value             # what slate has saved you in this repo — measured
```

Every `read`, `status`, and `sync` also leaves a one-line **receipt** of the
value it just delivered, so the savings stay visible as you work:

```
value: served 4,183 tokens of trusted context — re-exploring measures 31,280 tokens (7 files + tree); ~27,097 input tokens avoided
value: caught 2 stale docs before an agent trusted them — 2 catch(es) all-time in this clone
value: healed 2 stale doc(s) in 87 ms, 0 tokens — a manual AI rewrite measures ~24,374 in + ~624 out tokens (≈$0.08 at list price)
```

Nothing is invented: counts come from real command runs, token numbers from
real file sizes in your working tree, timings from a real clock. Dollar
figures are labeled estimates (4 chars/token, published list prices) computed
from those measured sizes — the same methodology as
[benchmarks/RESULTS.md](benchmarks/RESULTS.md). The ledger lives in
`.git/slate/value.json` (per-clone, never committed, never part of trust
math); set `SLATE_NO_VALUE=1` to turn receipts off.

Every context doc carries freshness metadata (sync anchor commit + content
digest + watch globs) in its frontmatter and is always in one of three states:

| Status | Meaning |
|--------|---------|
| `fresh` | nothing watched changed since the doc was synced — or something did, but the doc provably still checks out (a fresh scan generates the same facts, and no hand-written claim references a changed path) |
| `stale` | watched code changed (committed *or* uncommitted) in a way the doc can't be proven to survive — verify before acting |
| `needs-verification` | the freshness anchor is gone *and* the content digest can't vouch for the doc — treat as a rumor |

Two properties keep the signal honest in real workflows: `stale` means *"sync
would actually change something"* — an edit inside a watched tree that doesn't
alter what the doc claims stays `fresh (content-verified)`, so the flag never
becomes ritual noise. And squash-merges/rebases don't nuke the layer: when the
commit anchor dies, the content digest proves the watched files still match
the last sync and the doc stays `fresh` (a `slate sync` re-anchors it).

## What it generates

```
AGENTS.md                 routing + trust protocol at the repo root (read first)
CLAUDE.md                 one-line `@AGENTS.md` import — see below
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

**Why a `CLAUDE.md` as well.** Claude Code reads `CLAUDE.md` and *not*
`AGENTS.md` — it treats AGENTS.md as another tool's format and only reads it
when importing from Codex ([docs](https://code.claude.com/docs/en/memory)). A
repo whose context layer hangs off AGENTS.md alone therefore ships Claude Code
nothing, and does it silently: the MCP server still connects and the docs still
sit in the tree. `slate init` writes a `CLAUDE.md` containing `@AGENTS.md` so
the layer actually loads; commit it alongside AGENTS.md, and add any
Claude-specific instructions below the import. If you already have a
`CLAUDE.md`, Slate never touches it — it tells you to add the one line.

## Install

```bash
pip install -e .          # Python ≥ 3.11, zero runtime dependencies
slate --version
```

Requires a git repository — Slate anchors freshness to git history.

## Does it actually beat "just ask the AI to write .md files"?

Measured on this repo itself ([benchmarks/RESULTS.md](benchmarks/RESULTS.md),
reproduce with `python benchmarks/benchmark.py`):

- **Session start:** an agent ingests **28,210 tokens** via `slate_read` vs
  ~56,100 rediscovering the repo by hand (**2.0×**) or ~271,000 for a full
  repo dump (**9.6×**) — with trust labels attached, which the baselines
  can't provide at any price.
- **Staying true:** replaying this repo's real history, **69% of commits
  invalidated at least one context doc**. Manually maintained .md files rot
  silently on every one of those; Slate flagged each and healed it with a
  **~110 ms, 0-token** deterministic sync (vs an estimated ~8.5M input tokens
  of model traffic to do the same maintenance by prompting).
- **Every Slate operation is sub-second, local, and free** — status, scores,
  scan, sync, and the full MCP round-trip.

> **The session-start ratio used to be 10× and 26.5×, and it fell to 2.0× and
> 9.6× — because this repo's own layer bloated.** `read-next.md` is 34 KB and
> `decisions.md` is 74 KB here, against ~2 KB per generated doc. Nothing in
> Slate prunes the human-owned docs: `read-next` is meant to be *rewritten*
> when the focus changes rather than appended to, and `decisions` is
> append-only by design. Budget for that, because the session-start cost is
> paid every session. It is also a caution about the ratio itself — it says as
> much about how disciplined the layer's owner is as about the tool.

## Security

Slate has no server, no telemetry, and zero runtime dependencies. It does change
your threat model in one specific way: its purpose is to make agents *trust*
`.slate/**`, so a docs-only PR can put text into every future session's context
window, and `slate status` stays green as long as the referenced code has not
moved. Review context-doc diffs like code, and consider `CODEOWNERS` on them.

Full threat model — including committed hook configs, `PATH` as a trust
boundary, and the limits of the agent write gates:
[SECURITY.md](SECURITY.md).

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

## Freshness the agent can't skip (Claude Code hooks)

MCP tools are *offered* to the agent, and offering isn't enough. Measured
across 25 real headless sessions, the agent made **0 calls to any `slate_*`
tool in 320 tool calls** — with the server connected and `AGENTS.md` telling it
to check freshness first ([benchmarks/agentbench/RESULTS.md](benchmarks/agentbench/RESULTS.md)).
A signal the model has to opt into competes with grep, and grep wins.

So Slate also delivers freshness as **hook-injected context**, which the model
never gets to decline:

```bash
slate agent hooks install     # writes .claude/settings.json (also done by `agent enable claude`)
```

| Hook | When | What it injects |
|------|------|-----------------|
| `SessionStart` | every session, including after compaction | the whole layer's trust state — which docs are fresh, which aren't, and why |
| `PreToolUse` | `Read`/`Edit`/`Write`/`NotebookEdit` | a warning **only** when that specific file is covered by a non-fresh doc's watches |
| `Stop` | the agent finishes a turn | the hand-written claims its own session left suspect — off by default, see below |

`slate agent hooks install --client codex|cursor|all` writes the equivalent
config for those agents, and the same freshness text is rendered for all three.
**Claude Code and Codex are both canary-verified; Cursor is untried.** Codex
was confirmed on `codex-cli 0.146.1`: all three events fire and Slate's
freshness arrives in the right envelope. Two Codex specifics worth knowing —
its hooks live in **`~/.codex/hooks.json`, your home directory, not the repo**,
so it is per-developer setup that cannot be committed; and it requires trusting
a hook config before running it (`/hooks`). `PreToolUse` fires on Codex but
rarely names a file, because Codex reads through shell rather than a structured
read tool — SessionStart and Stop are the useful signals there. Cursor has not
been run at all; treat it as experimental.

Verified end-to-end, not assumed: in a repo with two deliberately stale docs, a
headless session named both docs, their suspect-claim counts, the anchor commit
and the culprit file — **in one turn, with zero tool calls**. Project
`.claude/settings.json` hooks do fire under `claude -p`, unlike `.mcp.json`,
which needs an explicit `--mcp-config`.

The `PreToolUse` hook is quiet by design — silent when everything is fresh,
silent on files no doc watches, and silent on the context docs themselves
(editing a stale doc is you healing it). A warning that fires on every tool
call is a banner, and banners get skimmed.

It costs ~380ms per covered file operation and is deliberately uncached: a
cache in the warning path is a way to suppress a warning that should have
fired. If `slate` isn't on `PATH` the hook fails and the session continues
normally — you lose the signal, never the session. Opt out with
`slate agent enable claude --no-hooks`; check wiring with `slate agent status`.

> Delivery into the context window is proven. Whether it changes *task
> outcomes* is not yet measured — the 0/25-correct benchmark has not been
> re-run against this path.

## Repairing the docs your session just invalidated

When your work moves the code a doc describes, `slate repair` names the exact
sentences at risk — the claim, the refs that put it at risk, the commits behind
them, and a file line to open. That much is read-only and always available.

Optionally, the agent can fix them and have the fix **checked before it lands**:

```bash
slate agent access full       # the write ceiling
slate agent repair on         # a second switch, off by default
```

Both are required. `slate_repair_apply` puts a rewrite through
`repair.verify_repair`, which refuses an edit that deletes the claim's code
references (that would drop it out of the trust surface entirely and turn the
doc green), that changes any other claim, or that moves the claim to a
different section. Leaving an accurate claim alone is an accepted outcome, not
a failure — most flagged claims on real history are still correct. A repair is
left unstaged and the doc is **not** re-anchored: freshness cannot score a
repair, because a repair is newer prose by definition.

**What this is measured to do, and what it isn't.** Two 20-trial sweeps
([E3-RESULTS.md](benchmarks/agentbench/E3-RESULTS.md)) found that turning the
switch on takes the layer from converging in 3/10 sessions to 10/10. But a
control with no repair loop still converged its own layer in 36–69% of trials —
the agent rewrites the docs by hand — and roughly half the treatment's
convergence never touched the gate either. So the honest claim is narrow:

> The layer often converges either way. What the repair loop buys is that about
> half of that convergence is **verified** rather than asserted.

No correctness effect was found in either direction (1/20 vs 1/20). And note
the hole: `verify_repair` guards the MCP path only. An agent with shell access
can edit a doc and run `slate mark` without any of this.

## Working in a team

Because the layer is synced and committed alongside the code, two branches
that both touch watched code otherwise conflict in every generated doc — and
resolving that the obvious way (`git checkout --ours`, then `slate sync`)
produces a correct auto-block while silently deleting the other branch's
hand-written notes. `slate merge install` fixes both:

```bash
slate merge install     # writes .gitattributes (commit it) + a per-clone driver
git add .gitattributes && git commit -m "slate merge driver"
```

The driver splits each doc the way sync does. Hand-written text gets a real
3-way merge, so both sides' notes survive and a genuine overlap still raises
markers. Generated facts aren't merged at all — the auto-block is a function
of the merged tree, so `slate sync` regenerates it correctly afterwards.
Watch globs are unioned, and the append-only decision log takes both branches'
entries instead of colliding.

Two things worth knowing:

- **`.gitattributes` is committed; the driver is per-clone.** Each teammate
  runs `slate merge install` once. A clone without it falls back to git's
  built-in merge — the behavior you have today, never anything worse.
- **The merge never invents freshness.** Freshness compares the anchor's tree
  to the merged worktree, so a doc that came through a merge describing only
  one branch's code is reported `stale` and healed by `slate sync` — exactly
  as if that code had landed on one branch.

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
├── merge.py          git merge driver: human text merged, facts left to sync
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
make test       # pytest (171 tests, real git repos in tmpdirs)
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

The repair loop — `slate repair`, the verification gate, the `Stop` hook and
`slate agent repair` — is built and measured end to end
([docs/repair-and-resume-plan.md](docs/repair-and-resume-plan.md), plan phases
0–5, which are numbered separately from the product phases here). Read the
measured limits above before pitching it: the layer converges with or without
it, and what it adds is verification of about half that convergence.

Remaining one-time setup (needs account owner): create the `slate-context`
project + trusted publisher on pypi.org, then push a `v0.2.0` tag; publish
the VS Code extension to the marketplace if wanted (works from a local VSIX
today). Phase 4 (team dashboards, merge policies, hosted bot) is not built.
