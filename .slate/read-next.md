---
slate_doc: read-next
slate_generated: false
slate_synced_commit: f5b574f
slate_synced_at: 2026-08-01T17:49:08+00:00
slate_synced_digest: 8e32443f6c6377c6
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
writes entries to `.claude/settings.json`: **SessionStart** (the layer's
whole trust state, empty matcher so it also covers `compact`) and
**PreToolUse** on `Read|Edit|Write|NotebookEdit` (warns only when the target
file is covered by a non-fresh doc's watches). Phase 3 added a third,
**Stop** — see below; it is installed inert and does nothing until both repair
switches are on. `slate agent enable claude`
installs them; `--no-hooks` opts out; `slate agent status` reports them.

Why this exists: the MCP path was measured and does not work — 0 `slate_*`
calls in 320 tool calls across 25 sessions. Hooks are not offered to the model,
so there is no choice to decline. The module computes **no trust math** (it
calls `freshness.evaluate_all` and renders, like `cli` and `mcp`), and every
entry point fails to *silence* — never to a false `fresh`, never to a broken
session. Pinned by `tests/test_claude_hook.py` (47 tests; 317 total).

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

**Repair tasks (Phase 1) — landed (2026-07-31).** New `slate/repair.py` +
`slate repair [--json]`: the suspect *hand-written* claims, strongest evidence
first, each with the refs that put it at risk, the commits behind them, and a
file line someone can open. `ClaimVerdict` gained
`doc_path`/`line`/`end_line`/`scope` (additive, as Part B was);
`freshness.symbol_files` went public because repair resolves a symbol ref to
its candidate files the same way the engine does. The worklist half is still
reads-only — no writes, no model, no second opinion about freshness — and the
gate added beside it in Phase 2 keeps all three properties.

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

**repairbench rev 1 ran and failed — inconclusively.** Pre-registration in
`spec.py` (committed before any agent ran), 36 trials, `spec.verdict()` → FAIL.
Superseded by rev 3 below, which is what `benchmarks/repairbench/RESULTS.md`
now describes; rev 1 survives there only as revision history. Its primary
number must not be quoted.

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

**repairbench rev 3 passed — Phase 0 is answered (2026-08-01). This is the
current state.** 24 trials on a *constructed* corpus: the agent rewrote 12 of 12
falsified passages and touched 0 of 12 still-accurate ones (Fisher exact
p=3.7e-07; pre-registered gate was a 40pp gap). Repair quality 10/12 mechanical,
12/12 on hand adjudication. Read `benchmarks/repairbench/RESULTS.md` before
touching any of this; the criteria are in `benchmarks/repairbench/spec.py`.

What made it measurable was abandoning mined ground truth. `corpus.py`'s
`build_trial` checks out a real Flask commit's parent, runs `slate init`,
commits an authored passage, then applies the `src/` half of that commit on top
— so the passage's truth value is known because it was *chosen* and the
falsifying diff is known because it was *applied*. No resolver stands between a
sentence and its evidence, which is what voided rev 1 (9 of 18 pairs carried
misattributed evidence). Three details are load-bearing and easy to undo by
accident: the prose commit must precede the code commit or `_prose_supersedes`
narrows the item out of the experiment; only the `src/` half is applied, because
`CHANGES.rst` entries exist in the falsified arm only and would be an answer key;
and `corpus.py --verify` must pass for all 24 before a run, which is what proves
Slate raises exactly one task naming exactly the applied commit.

**The control arm is the finding, not the treatment arm.** 12 declines, each
reasoning about whether the change intersects *what the sentence claims* — one
declined because the annotation that changed was a return type "which the
passage doesn't reference". That judgement is precisely what `slate repair`
cannot make and why `RepairTask.scope` exists.

**Two instrument defects, both conservative, both left unfixed on purpose.**
`corpus.asserts` applies its negation check to the *new* fact as well as the old,
so a rewrite that names the new behaviour and then contrasts it ("no longer a
`MethodViewType` metaclass") is scored as not having stated it. And `t08`'s
`old_fact` pattern named a clause its commit never falsified — an authoring
error, one in 12, down from 13 in 18 at rev 1. Both push the score *down*, so
neither can have manufactured the PASS, and fixing-then-rescoring recorded text
would be choosing the metric to fit the result. A rev 4 must run fresh sessions,
and there is no reason to spend them: 83% already cleared a 70% bar.

**Phase 2 — the verification gate — landed (2026-08-01). This is the current
state.** `repair.verify_repair(before, after, target)` returns a `Verdict` of
`repaired` / `unchanged` / `rejected`, and it decides *admissibility of an edit*,
never freshness. It is pure — the two doc bodies and `claims.human_claims`, no
tree, no git, no scan, no model — because the drafted `(root, doc, ...)`
signature handed a purely textual check a handle to the repo, which is how it
would grow a second opinion about trust.

Three things must hold, all about damage rather than truth: the target claim
still exists in its own section *carrying refs*; nothing else moved; and
"no change needed" is a pass. The first is the one that matters —
`claims._emit` only emits a unit that references code, so an agent can "repair"
a claim by deleting its backticks, the claim vanishes from `human_claims`, and
the doc goes green. `test_repair_cannot_manufacture_fresh` demonstrates that
rather than assuming it: it asserts the doc really does turn `fresh` after the
refs are stripped, then that the gate refuses the edit. Located by *section*,
not line — a rewrite reflows the paragraph it replaces, so an exact line would
reject the ordinary case.

**Phase 3 — session-end delivery — landed (2026-08-01). This is the current
state.** The repair loop is wired end to end: `claudehook.session_end_text`
names the suspect claims when the agent finishes a turn, `slate_repair_tasks`
lists them in full, and `slate_repair_apply` puts a rewrite through
`repair.verify_repair` before anything is written.

**The event is `Stop`, not `SessionEnd` — this was measured, not chosen.** A
canary against a real session found `SessionEnd` has no decision control and no
`additionalContext` whatsoever: it fires after the session is over and shows
stderr to the user, so nothing it emits reaches the model. The plan's drafted
"`SessionEnd`/`Stop` … `additionalContext` only" was not implementable. `Stop`
accepts `additionalContext` and *continues the conversation*, which is the only
way an end-of-session job can be acted on — and is why it needs brakes. Two,
independent: the client's `stop_hook_active` (observed `False` then `True`
across one continued turn) and a per-session note reusing `_already_announced`.
No `decision: "block"` anywhere; blocking is how a hook becomes the reason a
session will not end.

**The same canary changed the copy.** An imperative instruction injected by a
hook reads as a prompt-injection attempt and gets refused — correctly. So
`session_end_text` names itself and the settings file it came from, reports what
it observed, and says leaving a claim alone is a correct outcome. It offers; it
never commands.

**Gated twice, and the conjunction is the point.** `agentcfg.repair_enabled`
requires `agent-repair` on *and* access `full`; either alone grants nothing,
because otherwise the repair file is a way around the access ceiling. Default
off. `slate agent repair on` warns when the other switch is still read-only.

Shipped as apply-behind-gates rather than the plan's propose-only: a proposal
the agent renders for a human to paste back gives it no path to the doc, and
Phase 4's primary metric — suspect claims at session end versus session start —
would then be zero by construction. Four consents replace it (off by default,
full access, the client's per-call prompt, and the verifier), and a repair
leaves the doc **unstaged and un-re-anchored**, so a human still decides.

**Where the arc stands.** Phases 0–3 complete. Phase 4 is next: `repair-off` vs
`repair-on`, pre-registered in `benchmarks/agentbench/spec.py` before running,
n ≥ 10. It needs no constructed stale arm — the agent's own edits stale the
layer naturally, which is what unblocks `STALE_DOC_COMMIT` being `None` at
revision 3. Phase 5 (ledger and pitch) untouched.

Most of what shipped in this arc was still *off-plan*: claims never being
evaluated at all, co-landing prose flagged as rot, package symbols falsely
fresh, `.rst` filenames read as symbols. Two false-`fresh` classes closed.
Chasing the pivot has been an excellent bug-finding strategy, and it took three
revisions of instrument before it was also a hypothesis test.

**Next, in priority order.** (0) **Phase 4 — measure the thing that is now
measurable.** Arms `repair-off` vs `repair-on` at revision 3, n ≥ 10,
pre-registered in `benchmarks/agentbench/spec.py` *before* running — the
discipline repairbench had to learn twice. Primary: suspect-claim count at
session end versus session start. Secondary: verified-repair rate, rejection
rate, cost delta. Kill criterion, stated in advance: if verified repairs do not
exceed rejections, or the layer does not measurably converge, the pivot failed
and gets reported the way `decoy_hits` was. **The live question is uptake, not
capability.** Phase 0 measured an agent handed a scoped task and asked for a
decision — 12/12 repaired, 12/12 correctly declined. It says nothing about
whether an agent picks up a repair job it was not asked about, and the
3-calls-in-687 MCP finding says the default is no. The `Stop` hook is the bet
that injecting the job beats offering it. Do not report Phase 3 as a win before
that number exists. (1) Replicate the cost effect with cost
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
- `repair.verify_repair` must stay pure and must never consult freshness. It answers "is this edit admissible", not "is this doc now accurate" — freshness cannot answer the second about a repair, because a repair is newer prose by definition and authorship narrowing reads a timestamp the repair just updated. Measured: replacing a stale sentence with "`engine.run` returns 9999 purple" turns the doc `fresh`. Re-anchoring stays with `freshness.evaluate` and `slate mark`.
- `additionalContext` on a `Stop` hook **continues the conversation**. A Stop path that speaks unconditionally is an infinite session: the agent finishes, the hook speaks, it finishes again. Both brakes have to stay — `stop_hook_active` from the client, and the per-session note via `_already_announced`. And never emit `decision: "block"` from any hook: that is how Slate becomes the reason a session will not end.
- `SessionEnd` cannot inject context. No decision control, no `additionalContext` — it fires after the session is over and shows stderr to the user only. Anything that must reach the model at the end of a turn goes on `Stop`. Verified with a canary, not read off a doc.
- Hook text must offer, never command. A bare imperative arriving through a hook reads as a prompt-injection attempt and gets refused — observed in the canary. `claudehook.session_end_text` names itself, names the settings file it came from, states what it observed, and says declining is a correct outcome.
- `agentcfg.repair_enabled` requires *both* `agent-repair` on and access `full`. Never let one imply the other: the repair file would become a way around the access ceiling, which is the only thing that ceiling is for.
- A repair may never be allowed to *remove* a claim's refs. `claims._emit` only emits a unit that references code, so stripping the backticks deletes the claim from the trust surface entirely and the doc goes green — a false `fresh` manufactured by the feature meant to prevent it. Pinned by `test_repair_cannot_manufacture_fresh`.
- Don't reintroduce the old `apps/`/`packages/`/`infra/` trees from git history (decision log 2026-07-15).
