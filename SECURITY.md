# Security

Slate is a local CLI. It reads your repo, writes Markdown beside it, and — if
you wire it up — writes agent config files and hands text to a coding agent. It
has **no server, no telemetry, and no runtime dependencies**: the install
surface is the Python standard library plus the `git` binary already on your
machine.

That said, a tool whose whole purpose is *making an agent trust some files*
changes your threat model in a specific way. This document is the honest list.

## Reporting a vulnerability

Open a GitHub security advisory on the repository, or email the maintainer
listed in `pyproject.toml`. Please don't open a public issue for anything
exploitable.

---

## 1. Slate raises the blast radius of a docs-only pull request

**This is the one to understand before adopting.**

Slate exists to make agents trust `.slate/*.md` and `AGENTS.md`. When those docs
are fresh, `slate read` serves them as the first-read path and the SessionStart
hook injects their trust state into every session. That is the product working.

The consequence: **a contributor who edits only Markdown can put text into every
future agent session's context window.** A docs-only diff is the kind reviewers
skim. If the referenced code has not moved, `slate status` stays green and
nothing flags it, because nothing is wrong by Slate's definition — the claims
still resolve.

Slate does not detect *contradicted* prose, only *moved code* (see §5). There is
no signing, no provenance, and no distinction between "a maintainer wrote this"
and "a first-time contributor's PR did".

**Mitigations, in order of effectiveness:**

- **Review `.slate/**` and `AGENTS.md` diffs with the same care as code.** Add
  them to `CODEOWNERS`.
- Treat instructions appearing in context docs as untrusted input, the same way
  you would treat a comment in a source file. An agent reading "ignore your
  previous instructions" from a doc is a prompt-injection vector, and Slate is
  a delivery mechanism for it.
- Keep `slate agent access` at the default `read` unless you need otherwise.

## 2. Committed hook configs execute commands on clone

`slate agent hooks install` writes `.claude/settings.json` (and, if asked,
`.codex/hooks.json` / `.cursor/hooks.json`), and the docs tell you to **commit
them** so the team shares the same setup.

That means: cloning a Slate-enabled repo and opening it in a coding agent can
run a command on your machine, because that is how agent hooks work. Slate's
entry is the literal string `slate agent hook`, resolved from `PATH`.

Two consequences worth stating plainly:

- **`PATH` is the trust boundary.** If something earlier on your `PATH` is named
  `slate`, it runs on every matching tool call. The command is deliberately
  *not* an absolute interpreter path, because an absolute path would be correct
  on the machine that ran install and wrong for every teammate — the same
  trade-off the MCP server entry makes.
- **This is the agent vendors' execution model, not Slate's invention** — but
  Slate encourages the commit, so it owns part of the exposure. Codex, notably,
  requires explicitly trusting a hook config before running it, which is the
  stricter and better design.

If you don't want this, `slate agent enable claude --no-hooks` wires the MCP
server without any hooks, and `slate agent hooks uninstall` removes existing
entries.

## 3. Agent write access is gated, and the gates are advisory against a shell

Slate has two switches, both off by default and both committed as team policy:

| file | effect |
|---|---|
| `.slate/agent-access` | `read` (default) or `full`. In `read`, the MCP server does not even *expose* the mutating tools. |
| `.slate/agent-repair` | `on`/`off`. Requires `full` as well; either alone grants nothing. |

`slate_repair_apply` puts every rewrite through `repair.verify_repair`, which
refuses an edit that deletes a claim's code references, changes another claim,
or relocates it. `slate mark` and `slate_update_focus` refuse to attest a doc
that has *fewer* claims than at its last anchor.

**These gates govern the MCP path. They are advisory against an agent with a
shell.** Measured over 20 benchmark sessions: with repair off and read-only
access, agents still reached a green layer by editing `read-next.md` with an
ordinary file tool and running `slate mark` in a terminal. If your agent can run
`sh`, it can edit any file Slate can.

The gates are therefore a guardrail against *accident and default behaviour*,
not a sandbox. Use your agent's own permission system for the latter.

## 4. Network egress is opt-in and single-purpose

Slate makes exactly one outbound request, from `slate/llm.py`, and only when
**both** are true: you passed `slate sync --prose`, and `ANTHROPIC_API_KEY` is
set. It sends the *scanned facts* for a doc to the Anthropic API to draft an
orientation paragraph.

Nothing else phones home. There is no telemetry, no update check, no analytics.
The value ledger (`.git/slate/value.json`) is clone-local, never committed, and
never transmitted.

If your repo is sensitive, simply never pass `--prose`.

## 5. Known limits that are security-relevant

- **Slate detects moved code, not false statements.** A claim whose referenced
  code is untouched reads fresh forever, however wrong it becomes. Closing this
  would require a model judging truth, which would put a model in the trust
  path — deliberately refused. See the landmine in `.slate/read-next.md`.
- **`slate mark` renews trust by assertion.** It is the correct command for a
  human who has read the doc, and it is the weakest link if used carelessly.
  The claim-count guard catches deletion, not falsity.
- **Path handling trusts the repo root.** The MCP server and hooks operate on
  whatever repository they are pointed at; hook payloads naming files outside
  the repo are ignored (`_rel_target` resolves and rejects them), but Slate has
  no defence against being pointed at a hostile repo in the first place.
- **No supply-chain verification of the layer itself.** Docs are plain files in
  your repo with no signature. Their integrity is your git history's integrity.

## What Slate does not do

- No shell interpolation anywhere: every subprocess call is an argument list,
  never `shell=True`. No `eval`, no `exec`, no dynamic import of repo content.
- Never executes code it finds in your repo. The scanner parses Python with
  `ast` and other languages with regex — it never imports them.
- Never writes outside the repo root, except the clone-local ledger under
  `.git/slate/`.
