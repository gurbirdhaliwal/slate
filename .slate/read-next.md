---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 2579234
slate_synced_at: 2026-07-27T19:17:02+00:00
slate_synced_digest: e3b0c44298fc1c14
slate_watches:
---

# Read next — current focus

The smallest useful context for the *current* task. Rewrite this
when the focus changes; run `slate mark read-next` after.

## Current focus

**Part A — symbol-level change detection — landed (2026-07-21).** The freshness
engine now resolves a changed watched file to the *symbols* it touched, so a
human claim about `context.get_auto_block` only stales when that function's
lines actually move — not when a docstring two functions over changes. New
`slate/symbols.py` (stdlib `ast` for Python, shallow regex for JS/TS),
`gitutil.changed_hunks` (per-file new-side line ranges from `git diff
--unified=0`), and `refs.extract_symbol_refs` (backticked `module.symbol`).
The rewire lives in `freshness._claims_still_check_out`; symbol resolution may
only ever *narrow* stale→fresh, and any unparseable/ambiguous file falls back
to path-level "assume stale". See the decision log entry dated 2026-07-21.

**Part B — claim-level trust — landed (2026-07-21).** Evaluation now yields a
per-claim verdict (fresh/stale/unknowable) plus a conservative doc roll-up, so
`slate status` reads "2 of 5 claims suspect" and names the sentence. New
`slate/claims.py` segments the human body into referencing units (its walk is
*total* — the union of a doc's claim refs equals its whole-text refs, so nothing
the trust path relies on is dropped); `freshness` adds `ClaimVerdict` +
`DocReport.claims`, reuses Part A's `_symbol_verdict`, and line-diffs the
generated facts. `verify` watch-quiet is now the fraction of claims that check
out. The doc-level status stays the authoritative whole-text roll-up in
`_claims_still_check_out` (never a false fresh); the breakdown is the finer view.
`--json` is additive (status/verify/diff gained claim fields; MCP mirrors them).

**Part C — dependency edges as tracked facts — landed (2026-07-21).** The
module-level import graph `imports.py` used only to suggest watches is now a
field on `RepoScan` (`scanner` computes it via `imports.compute_edges`, parsing
reused not forked) and renders as a deterministic "Module boundaries (scanned)"
section in the architecture auto-block. Crossing a module boundary now
regenerates the block differently, so the existing freshness/sync machinery
flags and heals it with no new trust code; each edge line is a Part B claim.
Rendering sorts sources and targets (byte-identical across `PYTHONHASHSEED`),
top-level-dir granularity only — no resolver, no false precision.

**Value ledger — landed (2026-07-24).** Slate now shows the user what it saves,
with measured evidence only. New `slate/value.py`: a clone-local ledger at
`.git/slate/value.json` (via `gitutil.state_dir`; never committed, never in
trust math) records real events — context tokens served vs. a measured
re-exploration baseline on every `read`, stale docs caught before use (deduped
per doc + sync anchor) on `status`/`diff`, and per-sync receipts (measured
wall-clock, 0 tokens, vs. the measured size of a manual AI rewrite of the
non-fresh docs). One-line `value:` footers on read/status/sync (human output
only — `--json` shapes gained only additive fields), a `slate value [--json]`
cumulative report with assumptions disclosed, additive `value` fields on MCP
`slate_read`/`slate_sync`, and `SLATE_NO_VALUE=1` to opt out. Methodology is
`benchmarks/benchmark.py`'s: stored numbers are measured; dollars are
display-time arithmetic at labeled list prices. Every record path is
best-effort — a ledger failure can never break a command
(`tests/test_value.py` pins this, dedupe, and the JSON contracts).

**Merge driver — landed (2026-07-24).** The context layer now survives
concurrent branches. New `slate/merge.py` + `slate merge install|uninstall|
status|run`: git calls `slate merge run %O %A %B %P`, which 3-way-merges the
hand-written text (`gitutil.merge_file` wrapping `git merge-file`), replaces
both sides' auto-blocks with a placeholder so generated facts never enter the
merge, restores the block from ours, and unions `slate_watches`. `DocSpec`
gained `append_only` (decisions only), switching that doc to `--union` so
concurrent decision entries never collide. Install has two halves with
different lifetimes: committed `.gitattributes` + per-clone
`merge.slate.driver`; a clone missing the driver degrades to git's built-in
merge, never to something worse. Keeping ours' anchor cannot manufacture a
false `fresh` because freshness diffs the anchor's *tree* against the merged
worktree — pinned by `test_merged_layer_is_not_falsely_fresh`. Known limit:
two branches appending prose at the same point still conflict honestly (git
can't know the order); neither side's note is lost.

**The precision-upgrade arc (A→B→C) is complete.** File→symbol→claim resolution
plus dependency-edge facts. Remaining carry-overs, both optional refinements
(not blockers): (1) the orphaned-anchor path is digest-gated (no baseline to
diff) — a safe narrowing compares the recorded digest against the digest *at
HEAD*, then resolves working-tree changes by symbol; (2) shallow resolution
treats `module.symbol` as living in `module` — re-export aliases aren't followed
(accepted bound, matches `imports.py`). A natural next arc is symbol-level edges
(which *symbol* imports which), but only if top-level-dir granularity proves too
coarse in practice.

**Hook-based delivery — landed (2026-07-27). This is the current focus.**
The consultation problem is closed on the delivery side. Slate no longer
*offers* freshness to Claude Code; it injects it. New `slate/claudehook.py` +
`slate agent hook` (the stdin handler) and `slate agent hooks install`, which
writes two entries to `.claude/settings.json`: **SessionStart** (the layer's
whole trust state, empty matcher so it also covers `compact`) and
**PreToolUse** on `Read|Edit|Write|NotebookEdit` (warns only when the target
file is covered by a non-fresh doc's watches). `slate agent enable claude`
installs them; `--no-hooks` opts out; `slate agent status` reports them.

Why this exists: the MCP path was measured and does not work — 0 `slate_*`
calls in 320 tool calls across 25 sessions. Hooks are not offered to the model,
so there is no choice to decline. The module computes **no trust math** (it
calls `freshness.evaluate_all` and renders, like `cli` and `mcp`), and every
entry point fails to *silence* — never to a false `fresh`, never to a broken
session. Pinned by `tests/test_claude_hook.py` (30 tests; 225 total).

**Measured (2026-07-27 sweep, 4 arms × 5 trials, all same-day).** Delivery
works and is verified end-to-end. What it buys is less settled:

- **The pre-registered metric failed.** `decoy_hits` was named in `spec.py` in
  advance as the thing hook delivery should move. It did not move (exact
  p=1.0) and went the wrong way directionally (1/5 → 2/5 trials).
- **An unplanned cost effect appeared, on the stale arm only.** tool calls
  41→31 (p=0.0159), turns 42→32 (p=0.0159), context 56.5K→41.5K (p=0.0079,
  the floor for n=5). The fresh arm showed nothing (p=0.44–0.69). Effect
  present where the layer is stale and absent where it is fresh is the
  interaction the mechanism predicts, and a confound like model drift would
  have moved both arms.
- **It is exploratory, not a win.** The three cost numbers are one behavioural
  change measured three ways (cache-creation per turn is 1,344 vs 1,294, so
  tokens track turns track tool calls). Eight tests, Bonferroni puts the best
  at the edge, n=5.
- **Correctness is still 0/5 in every arm** (0/35 cumulative). Nothing claims
  context makes an agent likelier to get a hard change right.
- **Offering still fails:** 3 `slate_*` MCP calls in 687 tool calls. Injecting
  reached every trial.

**Do not repeat this measurement mistake.** `hook_injections` cannot see
PreToolUse — Claude Code writes SessionStart's injected context into the
stream-json transcript and not PreToolUse's, so the raw count reads as
"PreToolUse never fired" when it fires every time. Confirmed by instrumenting
the hook command to log its own invocations. The metric is a *floor* on
delivery and cannot attribute the effect to either hook.

**Next, in priority order.** (1) Replicate the cost effect with cost
*pre-registered* and higher n, and run SessionStart and PreToolUse as separate
arms — right now the sweep cannot say which hook did the work. (2) The old
`benchmarks/RESULTS.md` + `benchmark.py` are still self-referential and
estimate-based, and its numbers predate the package-granularity scanner —
re-run or retire it; the repo ships two RESULTS.md files making different
kinds of claim. (3) Portability: `claudehook.py` splits cleanly into
agent-neutral rendering (`session_start_text`, `pre_tool_use_text`,
`_covering`) and a Claude-specific surface (`_rel_target`, `_output`, the
settings writer). Codex uses the same event names via `hooks.json` /
`[hooks]` in `config.toml`; Cursor uses `.cursor/hooks.json` with different
names (`beforeReadFile`, `afterFileEdit`) and is still beta. Only worth
porting once the effect replicates. (4) `InstructionsLoaded` (no decision
control, side effects only) would turn "the layer loaded" into a logged fact.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Neither must the hook — `slate/claudehook.py` renders `freshness.evaluate_all` and nothing else. A second implementation of "is this doc fresh" is a second thing that can disagree, and it would disagree inside the model's context window.
- A hook that raises degrades the session it was meant to inform. Every path in `claudehook` resolves to silence + exit 0; don't add one that can throw.
- Claude Code reads `CLAUDE.md`, not `AGENTS.md`. Project `.claude/settings.json` hooks *do* load under `claude -p`; project `.mcp.json` does **not** without `--mcp-config`. Verify delivery with a canary before trusting any agent-behaviour measurement.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
