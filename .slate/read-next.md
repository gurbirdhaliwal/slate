---
slate_doc: read-next
slate_generated: false
slate_synced_commit: 5384232
slate_synced_at: 2026-07-27T13:58:22+00:00
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

**What is proven and what is not.** Delivery is verified end-to-end: in a repo
with two deliberately stale docs, a headless session named both docs, their
claim counts, the anchor commit and the culprit file in one turn with zero tool
calls, and reproduced the PreToolUse warning verbatim on reading a covered
file. **Task-level outcomes are NOT measured** — the 0/25-correct sweep has not
been re-run against this path. Do not claim an accuracy win.

**Next, in priority order.** (1) Re-run `benchmarks/agentbench` against
hook-based delivery (~90 min, one sweep) — the harness is reusable and this is
now the question worth answering; note the handoff's caution that n=5 did not
survive its error bars, so consider more trials or a sharper task. (2) The old
`benchmarks/RESULTS.md` + `benchmark.py` are still self-referential and
estimate-based, and its numbers predate the package-granularity scanner —
re-run or retire it; the repo currently ships two RESULTS.md files making
different kinds of claim. (3) `InstructionsLoaded` (no decision control, side
effects only) would turn "the layer loaded" from an assumption into a logged
fact — the natural answer to the per-client verification the CLAUDE.md decision
entry called for.

## Landmines

- After changing code under `slate/` or `tests/`, run `slate sync` and commit the doc updates in the same PR — CI's `slate status --ci` gate fails otherwise.
- The MCP server must never compute trust math or expose write tools in read mode; `tests/test_mcp.py` pins both.
- Neither must the hook — `slate/claudehook.py` renders `freshness.evaluate_all` and nothing else. A second implementation of "is this doc fresh" is a second thing that can disagree, and it would disagree inside the model's context window.
- A hook that raises degrades the session it was meant to inform. Every path in `claudehook` resolves to silence + exit 0; don't add one that can throw.
- Claude Code reads `CLAUDE.md`, not `AGENTS.md`. Project `.claude/settings.json` hooks *do* load under `claude -p`; project `.mcp.json` does **not** without `--mcp-config`. Verify delivery with a canary before trusting any agent-behaviour measurement.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
