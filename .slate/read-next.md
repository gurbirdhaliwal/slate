---
slate_doc: read-next
slate_generated: false
slate_synced_commit: a816805
slate_synced_at: 2026-08-01T01:40:10+00:00
slate_synced_digest: 80b964d93058cd4e
slate_watches:
  - benchmarks/**
  - slate/**
  - tests/**
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

**Hook-based delivery — landed (2026-07-27).**
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

**The claim-bearing docs were never checked — fixed (2026-07-30). This is the
current focus.** Across all 54 commits of this repo's history, zero human
claims were ever evaluated. Not "none were stale" — none were *checked*.
`read-next` (11 claims) and `decisions` (7) carried no watches, and
`freshness._evaluate` returns `fresh` before reading the body when the watch
list is empty; the three watched docs carry no prose refs at all. The two sets
were disjoint, so Part B's human half had never executed in either direction.
`context.default_watches` now makes `read-next` watch-based; `decisions` stays
attested (append-only — a past decision stays true about the past).

Re-walking history with watches injected found real rot: read-next claimed
"top-level-dir granularity only — no resolver" for 4 commits after `da71aae`
made the map package-level *and* added a resolver. That is the failure Slate
exists to prevent, in Slate's own layer, undetected for its whole life.

**Authorship narrowing — landed (2026-07-30).** A claim whose prose was written
at or after the change to the code it names is fresh: `_prose_supersedes` in
`freshness`, over `gitutil.blame_lines` / `is_ancestor` / `last_change_commit`.
Prose and code landing in one commit is not rot, but the doc's anchor predates
that commit, so the claim was flagged the moment it was written — 6 of 31 flags
(19%), the largest false-positive class. Measured both arms through identical
code paths with only the narrowing toggled: 31 → 25 hit-instances. Narrowing
only, like symbol resolution: every unanswerable question returns False and
leaves the verdict alone. `Claim` gained `end_line` so the whole span is blamed,
and `ContextDoc.body_line` maps a body line to a file line. Also fixed:
`_claims_still_check_out` returned False outright for `generated: false` docs,
which made a watched `read-next` permanently stale regardless of its claims.

It covers **both** ref kinds. A symbol ref resolves through `_symbol_files` to
the changed code files that could host it — the named module, or *every*
changed code file when the qualifier is unresolvable, so prose must be newer
than all of them before it narrows. On this repo's live working tree that took
suspect claims from 8 to 4; on the historical corpus it changes nothing, since
those flags are genuinely older than their code.

Cost: whole-doc blame (one `git blame` per doc, not per claim) plus a
per-evaluation answer cache `_GIT_ANSWERS`, cleared at the top of
`evaluate_all`/`evaluate_doc` so a long-lived MCP process never reads a stale
commit. ~500ms vs ~406ms unnarrowed on this repo — 23%, against 78% before
those two fixes.

**Residual over-flagging is a prose problem, not a math problem.** The
remaining flags are all "the file changed after the sentence was written" —
legitimate, but a path ref puts a claim at risk without falsifying it. Prose
that names `` `module.symbol` `` instead of `` `path/to/file.py` `` is narrowed
by Part A *and* dated precisely by authorship. That is a writing convention,
not an engine change. Known bound: a claim spanning both new and old prose
blames to the oldest line, so an old paragraph gaining a new ref stays flagged.
Conservative on purpose — the safe direction.

**Repair tasks — landed (2026-07-31). This is the current focus.** New
`slate/repair.py` + `slate repair [--json]`: the suspect *hand-written* claims,
strongest evidence first, each with the refs that put it at risk, the commits
behind them, and a file line someone can open. `ClaimVerdict` gained
`doc_path`/`line`/`end_line`/`scope` (additive, as Part B was);
`freshness.symbol_files` went public because repair resolves a symbol ref to
its candidate files the same way the engine does. Reads only — no writes, no
model, no second opinion about freshness.

Two scoping calls worth keeping. **Generated facts are not repair tasks**:
`slate sync` already rewrites the auto-block deterministically for zero tokens,
and over this repo's whole history generated drift was the *only* staleness
that ever occurred, so routing it to a model would be strictly worse. And
`scope` distinguishes `symbol` (the named symbol provably moved) from `path`
(a file changed somewhere) — on the corpus most path-scoped flags were prose
that was still accurate, so **anything consuming these tasks must let "this
claim is still correct" be an answer**, or its default action on the common
case is rewriting correct prose. That constraint also lands on Phase 2: the
verification gate has to accept "no change needed" as a verifiable outcome,
not only "the claim now checks out".

**Freshness cannot score a repair — measured (2026-07-31). Read this before
touching Phase 2.** The plan's original criterion was "an agent's rewrite makes
Slate's own verifier turn the claim fresh". It is circular. Authorship
narrowing clears a claim whose prose is newer than the code it names, and a
repair is newer prose by definition, so freshness reads a timestamp the repair
just updated. Demonstrated: replacing a stale sentence with `` `engine.run`
returns 9999 purple`` turns the doc **fresh**. The criterion would have scored
~100% for an agent writing garbage, and the plan's Phase 2 gate — "require the
target claim becomes fresh" — would accept nonsense from every trial. The gate
must rest on signals a repair cannot move by existing.

**repairbench rev 1 ran and failed — inconclusively. Read
`benchmarks/repairbench/RESULTS.md` before touching this.** Pre-registration in
`spec.py` (committed before any agent ran), 36 trials, `spec.verdict()` → FAIL,
so under the terms fixed in advance **Phases 2 and 3 are not built and
`slate repair` stays a read-only list.** That conclusion stands; the primary
number behind it does not, and must not be quoted.

Why it is void: the metric scored *unchanged text* (the agent declined 16 of
18), the resolver could not express Flask's API, and it punishes accurate prose
about deletions — "the `flask.ext` package has been removed" is true and names
something that by definition no longer exists. The control comparison is void
too: both arms declined at ~88%, so there is no discrimination signal, and the
control threshold passed while measuring nothing.

Hand-adjudication then found the corpus itself conflated *a maintainer edited
this* with *this was false*: 8 of 18 were editorial rewrites and 9 of 18
carried evidence resolved to the wrong file, leaving **5 usable pairs**. On
those 5 the agent declined 5 of 5 — a direction, not a result.

**Symbol refs resolve by module path, not filename stem — landed (2026-07-31).
This closed a false `fresh`.** `_changed_symbols` now carries a dotted module
path (`_module_path`: `src/flask/views.py` → `flask.views`, `pkg/__init__.py`
→ `pkg`) and `_symbol_verdict` matches a ref's qualifier against it via
`_qualifies`, taking the full dotted prefix when the ref carries one.

Stem matching was not merely imprecise. A claim about `pkg.request` whose
symbol lives in `pkg/__init__.py` never matched — that file's stem is
`__init__` — and when any unrelated `fixtures/pkg.py` existed, the qualifier
counted as "known" and *suppressed the conservative fallback* that would
otherwise have caught it. The claim came back **fresh** while the code it
described had moved. Flask has exactly that shape: a test fixture named
`flask.py` beside the real package. Pinned by
`test_package_symbol_with_a_same_named_decoy_is_not_falsely_fresh`, plus a
src-layout case and a no-over-flagging case in the other direction.

**References to code outside the repo — measured, mostly a non-problem
(2026-07-31).** This was written up as the next blocker and that was wrong; it
was checked before being built, and module-path resolution had already closed
most of it. A doc citing stdlib `logging.Formatter` in a repo that has its own
`app/logging.py` stays **fresh** when that module changes, because resolution
sees the module never defined `Formatter`.

Two cases remain, both conservative: an *unparseable* local module leaves the
claim `unknowable`, and a local module that genuinely defines `Formatter`
leaves it `stale`. `sys.stdlib_module_names` would clear both and should not
be used for it — that trades a false `stale` for a possible false `fresh`,
since a doc writing `logging.Formatter` about its *own* module would then
never be flagged. Only one of those errors is permitted. All three behaviours
are pinned in `tests/test_freshness.py`.

**Where the arc actually stands.** Of the plan's phases, only **Phase 1** is
complete — and it was built out of order, as Phase 0's instrument. **Phase 0 is
still the open one**: it has consumed a full experiment cycle, had its exit
criterion rewritten mid-flight for circularity, and still has no usable answer.
Phase 2 is worse than not-started — both drafted gates are dead (freshness is
circular; `refs_resolve` cannot express deletions), so it has no working design.
Phases 3–5 untouched.

Most of what shipped in this arc was *off-plan*: claims never being evaluated
at all, co-landing prose flagged as rot, package symbols falsely fresh, `.rst`
filenames read as symbols. Two false-`fresh` classes closed. Chasing the pivot
has been an excellent bug-finding strategy and a poor hypothesis-testing one.

**Next, in priority order.** (0) **rev 2, with ground truth *constructed*
rather than *discovered*.** Every attempt to mine a corpus from real repos has
foundered on ref resolution, and each fix narrows the problem without solving
corpus scale. Instead: take a real repo, make a real code change, and write the
sentence that describes the old behaviour. Real prose, real diff, exact ground
truth, no resolver in the loop. Design it before running anything — and note
that rev 2 needs `spec.REVISION` bumped, the discrimination metric expressed as
a *difference between arms* rather than a threshold on one, and the control
matching fixed (10 of 18 controls skipped in rev 1 because the corpus stores
segmenter-normalised text that no longer matches the file byte-for-byte).
(1) Replicate the cost effect with cost
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
- Neither must the hook — `slate/claudehook.py` renders what `freshness.evaluate_all` and `cochange` already computed, and derives no trust of its own. A second implementation of "is this doc fresh" is a second thing that can disagree, and it would disagree inside the model's context window.
- A hook that raises degrades the session it was meant to inform. Every path in `claudehook` resolves to silence + exit 0; don't add one that can throw.
- Claude Code reads `CLAUDE.md`, not `AGENTS.md`. Project `.claude/settings.json` hooks *do* load under `claude -p`; project `.mcp.json` does **not** without `--mcp-config`. Verify delivery with a canary before trusting any agent-behaviour measurement.
- `slate sync` cannot clear `read-next`. It has `generated: false`, so there is no auto-block to regenerate — only `slate mark read-next` re-anchors it, and only after someone has actually rewritten the focus text. Marking a doc you have not read is the one way to turn this whole layer back into a rumor.
- Authorship narrowing may only ever narrow. `freshness._prose_supersedes` must return False for every question it cannot answer — no blame, no anchor, no file. A `git` call that starts *assuming* recency is a false `fresh` with extra steps.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
