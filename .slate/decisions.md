---
slate_doc: decisions
slate_generated: false
slate_synced_commit: 3b26748
slate_synced_at: 2026-08-01T01:32:31+00:00
slate_synced_digest: e3b0c44298fc1c14
slate_watches:
---

# Decision log

Append-only. One entry per decision that a future reader (or AI)
would otherwise re-litigate.

```
Date: YYYY-MM-DD
Decision:
Rationale:
Trade-off:
Revisit trigger:
```

The full strategic log lives in `slate-product-doc.md` §14; entries here are
the repo-level calls an AI session needs at hand.

```
Date: 2026-07-15
Decision: Pivot — Slate is a repo-local context control plane CLI; the entire
          hosted stack (Spring API, workers, Postgres, dashboard) was deleted.
Rationale: Stale-context pain is universal and day-one; the debugger wedge
          needed production traffic before delivering value.
Trade-off: Revenue deferred to the team layer (Phase 4).
Revisit trigger: Freshness signal doesn't change user behavior after ~8 weeks.

Date: 2026-07-15
Decision: Zero runtime dependencies; freshness derived from git at read time,
          never stored; no LLM anywhere in the trust math.
Rationale: Trust signals must be reproducible, explainable, and free.
Trade-off: Hand-rolled frontmatter + glob matching (~120 lines, tested).
Revisit trigger: Real need for full YAML or gitignore-style negation.

Date: 2026-07-15
Decision: The local freshness gate is a pre-PUSH hook, not pre-commit.
Rationale: Syncing is two commits (code, then re-anchored docs); a pre-commit
          gate fails exactly when committing the code. Push time checks the
          branch tip — the same contract CI enforces.
Trade-off: Staleness caught minutes later than commit time.
Revisit trigger: Anchoring by content hash instead of commit SHA.

Date: 2026-07-15
Decision: LLM prose (`sync --prose`) is an injected callback that can only
          prepend prose above the scanned facts; failures degrade to plain sync.
Rationale: Keeps the §8 boundary mechanical — the model cannot alter facts,
          statuses, or scores by construction.
Trade-off: raw urllib, no SDK conveniences.
Revisit trigger: Prose grows beyond one paragraph per doc.
```

```
Date: 2026-07-21
Decision: Module dependency edges are tracked facts (Part C). The import graph
          `imports.py` computed only to propose watches is now a field on
          `RepoScan` (via `imports.compute_edges`, parsing reused not forked)
          and renders as a deterministic "Module boundaries (scanned)" section
          in the architecture auto-block. No new freshness code: a changed edge
          set regenerates the block, so `_claims_still_check_out` + the sync
          preview flag and heal it; each edge line is a Part B claim.
Rationale: The auto-block was a directory census that rarely changes, giving the
          freshness engine little semantic surface. Dependency edges are exactly
          the fact that moves when architecture shifts — but they were discarded,
          so a new cross-module import produced no signal (invisible drift).
Trade-off: Top-level-dir granularity only — shallow, resolver-free, no false
          precision (an intra-dir import is not an edge). Rendering sorts sources
          and targets so identical repo state is byte-identical across hash seeds
          — a flaky fact manufactures false stale, as corrosive as a false fresh.
Revisit trigger: Top-level-dir edges prove too coarse (want symbol-level edges),
          or a repo where the shallow regex import parse misleads.

Date: 2026-07-21
Decision: Trust resolves at the claim, not the doc (Part B). Evaluation yields a
          per-claim verdict (fresh/stale/unknowable) plus a conservative doc
          roll-up; the score's watch-quiet component becomes the fraction of
          claims that check out. New `claims.py` segments the human body into
          referencing units; `freshness` adds `ClaimVerdict`/`DocReport.claims`
          and line-diffs the generated facts; `verify`/`diffs`/`cli`/`ui`/`mcp`
          surface it. `--json` is additive only (VS Code + PR bot unchanged).
Rationale: One label per doc drags a solid doc amber for a single suspect
          sentence and never tells the AI *which* sentence to re-verify
          (product doc §1 pain #5). Part A already knows which symbol changed;
          Part B attributes it to the claim that references it.
Trade-off: The doc-level status stays the authoritative *whole-text* roll-up in
          `_claims_still_check_out` (not `all(claim fresh)`) so a claim the
          segmenter might miss can never sneak a doc to fresh — the breakdown is
          the finer view, the whole-text scan is the §10 safety net. Claim
          segmentation is deterministic markdown-block splitting, no parser.
Revisit trigger: A claim the segmenter drops that the whole-text roll-up
          catches (status stale, zero suspect claims shown); or a need to score
          generated vs human claims with different weights.

Date: 2026-07-21
Decision: Freshness resolves a changed watched file to the symbols it touched
          (Part A). `_claims_still_check_out` now clears a human claim about
          `module.symbol` only when that symbol's lines were provably untouched;
          a claim about a whole *path* still stales on any edit (unchanged).
          New: `symbols.py` (stdlib `ast` for Python, shallow regex for JS/TS,
          in the spirit of `imports.py`), `gitutil.changed_hunks` (new-side line
          ranges from `git diff --unified=0`, untracked files reported whole),
          `refs.extract_symbol_refs`. No frontmatter/schema change.
Rationale: Watch globs resolve at the file; claims live at the symbol. The old
          rule ignored `module.symbol` refs entirely — a body change to a
          described function was a silent false *fresh* (the path was never
          backticked and the coarse auto-block regenerates identically).
Trade-off: Symbol resolution may only *narrow* stale→fresh; any unparseable or
          ambiguous file (SyntaxError, deleted, non-Python/JS, unresolvable
          qualifier) falls back to path-level "assume stale" — never a false
          fresh (§10). Re-export aliases aren't followed (shallow, no resolver).
Revisit trigger: Any observed false fresh from symbol resolution; a real need
          to follow re-exports or to narrow the orphaned-anchor (digest) path.

Date: 2026-07-16
Decision: Agent integration = MCP stdio server + two-layer consent: editor prompts per call, .slate/agent-access is the read-default capability ceiling
Rationale: MCP is what coding agents already speak; a server-side ceiling caps the blast radius of an over-eager always-allow and is committable team policy
Trade-off: Two config surfaces to explain (editor allowlist + access file)
Revisit trigger: MCP framing churn, or read-default friction blocking adoption
```

```
Date: 2026-07-20
Decision: Freshness hardened against the two premortem failure modes: (1) stale
          requires proof of impact — if a fresh scan regenerates the identical
          auto-block and no human section references a changed path, the doc is
          fresh (content-verified), changed paths kept as evidence; (2) every
          stamp records slate_synced_digest (sha256 of watched files' content),
          and an orphaned commit anchor falls back to it — match = fresh,
          mismatch = stale, absent = needs-verification.
Rationale: (1) Broad watch globs flagged ~half of all commits; an always-yellow
          signal gets ignored and the sync ritual becomes noise. (2) Squash-merge
          (the GitHub default) orphaned every anchor, degrading the whole layer
          to a 0.25-capped rumor in every fresh clone and CI checkout.
Trade-off: status may run a repo scan when watched paths changed (still
          sub-second); digest mismatch can't enumerate committed paths.
Revisit trigger: Any observed false fresh from content verification; digest
          hashing felt (>1s) on large repos.
```

```
Date: 2026-07-24
Decision: Quantified-value surface — measured one-line receipts on every
          read/status/sync, a `slate value` cumulative ledger, and additive
          "value" fields on MCP slate_read/slate_sync. Ledger is clone-local
          (.git/slate/value.json), never committed, entirely outside trust math.
Rationale: The user should see what Slate saves on every run, not take it on
          faith — and a context-trust product cannot hallucinate its own
          marketing. The ledger stores measured events only (real file sizes,
          real runs, real wall-clock); token/dollar figures are display-time
          arithmetic under the same stated assumptions as benchmarks/benchmark.py.
          Catches dedupe per (doc, sync anchor); fresh-doc syncs record nothing
          avoided; small repos where the layer exceeds the baseline are reported
          as exactly that.
Trade-off: read/sync now run a freshness/scan pass for measurement (sub-second,
          local); one clone-local state file inside .git. Recording is
          best-effort by construction — a ledger failure never breaks a command.
Revisit trigger: Receipts reading as noise in the field, or evidence the
          exploration baseline misstates real agent behavior.
```

```
Date: 2026-07-24
Decision: A git merge driver owns the context layer on merge (`slate merge
          install`). Human-written text gets a real 3-way merge; both sides'
          auto-blocks are placeheld out and the block is left to `slate sync`,
          because it is a pure function of the merged tree. Frontmatter is
          taken from ours, except `slate_watches`, which is unioned. The
          append-only decision log merges with --union (new `DocSpec.append_only`)
          so two branches' entries never collide.
Rationale: The documented workflow syncs and commits docs alongside the code,
          so every sync rewrites the anchor plus the block and *every*
          concurrent PR pair conflicted in all four generated docs. Worse, the
          obvious fix (`git checkout --ours` + `slate sync`) yields a correct
          auto-block while silently deleting the other side's prose — the same
          class of bug as clobbering human edits on sync (§4), but invisible.
Trade-off: Two-part install with different lifetimes — .gitattributes is
          committed, `merge.slate.driver` is per-clone, so each teammate runs
          `slate merge install` once. A clone without the driver falls back to
          git's built-in merge, i.e. today's behavior, never something worse.
          Two branches appending prose at the same point still conflict
          honestly; git cannot know the intended order.
Safety:   Keeping ours' anchor cannot manufacture a false `fresh`. Freshness
          diffs the anchor's *tree* against the merged worktree (`git diff
          <anchor> HEAD`, not the `anchor..HEAD` range), so watched paths that
          differ are reported no matter which branch they came from or whether
          the anchor is an ancestor. A squashed anchor falls to the digest,
          recomputed against the merged tree. Pinned by
          tests/test_merge.py::test_merged_layer_is_not_falsely_fresh.
Revisit trigger: A merge that loses human text, or field evidence that the
          prose-append conflict is frequent enough to want section-aware merging.
```

```
Date: 2026-07-26
Decision: The module map and the dependency graph are derived at *package*
          granularity, not first-path-segment. `_build_modules` descends
          through pass-through directories (`src/` -> `src/flask/`) and breaks
          out sub-packages holding >= 2 code files, capped at 14 rows with
          supporting trees (tests/, examples/, docs_src/) yielding first.
          `imports.compute_edges` resolves dotted import names against the
          repo's real package layout instead of matching first segments.
Rationale: Measured on eight well-known Python repos, the old heuristic
          returned 2-5 module rows regardless of size — 4 rows for FastAPI's
          1,130 files, the same 3 as for a 37-file repo — and 3 of 8 reported
          "no cross-module imports detected", because `from flask.json import
          x` names no directory called `flask`. Slate's own layout is flat
          (`slate/`, `tests/`), so dogfooding structurally could not surface
          this: every probe repo using the standard `src/<pkg>/` layout got a
          context layer that answered none of the "where does X live"
          questions modules.md exists to answer.
Trade-off: Row selection is heuristic (threshold, cap, supporting-root list) —
          §10 "vibecode freely" territory. Deliberately shallow: one level of
          sub-package per source root, no resolver. A monorepo gets one row per
          workspace package rather than a full tree.
Safety:   Watch globs did NOT follow the map down. `RepoScan.source_dirs` stays
          top-level and still feeds `context.default_watches`; a `src/flask/**`
          watch would stop watching anything else later added under `src/`, and
          an unwatched change is a false `fresh` — the one failure §10 forbids.
          Watch inference projects the module-path graph back up to top-level
          before proposing, so suggestions only ever widen the net. The
          import-name index only falls back to basename matching at depth 1, so
          a vendored `src/pkg/json/` cannot swallow `import json` and invent an
          edge. Pinned by tests/test_src_layout.py (9 of its 12 tests fail
          against the previous scanner; the 3 that pass are the anti-narrowing
          invariants, which must hold in both).
Revisit trigger: A repo shape where one level of sub-package is too shallow to
          orient in, or field evidence that the 14-row cap hides real source.
```

```
Date: 2026-07-26
Decision: `slate init` (and `slate agent enable claude`) also writes a
          `CLAUDE.md` containing `@AGENTS.md`. An existing CLAUDE.md is never
          modified — Slate reports what to add and exits. The file is listed in
          `CONTEXT_DOC_PATHS` so it cannot invalidate the layer it points at.
Rationale: Claude Code loads CLAUDE.md and never AGENTS.md; it treats AGENTS.md
          as a foreign format, read only when importing from Codex. Slate hangs
          its entire layer off AGENTS.md, so every Slate repo shipped Claude
          Code nothing — silently, because the MCP server still connects and the
          docs still sit in the tree. Measured, not inferred: a canary
          instruction in AGENTS.md was ignored in 3/3 headless runs and the same
          text in CLAUDE.md was followed every time; a 25-session benchmark run
          on this assumption produced five arms that were all secretly context-
          free. The `@` import is the remedy Anthropic's own docs prescribe.
Trade-off: A second, vendor-specific file at the repo root. A symlink would
          avoid it but needs Administrator or Developer Mode on Windows, so the
          import is the portable choice. Slate now writes a file for one
          specific client, which sets a precedent: adding one per client does
          not scale, and the real fix is per-client verification, not per-client
          files.
Safety:   The bridge makes no claims about the code, so it is a context-layer
          path rather than a tracked doc — no frontmatter, no freshness. It is
          in CONTEXT_DOC_PATHS because a repo with no source directories has the
          module map watching `**`, where an unexcluded bridge would stale a doc
          the moment Slate wrote it. Never clobbering an existing CLAUDE.md is
          the load-bearing rule: overwriting a user's instructions to install a
          pointer would be a worse bug than the one being fixed. Pinned by
          tests/test_claude_bridge.py, including that an import inside a code
          fence does not count as wired (Claude Code skips fenced blocks, so
          reporting it as live would leave the user believing the layer loads).
Revisit trigger: Claude Code adding native AGENTS.md support (then drop the
          bridge), or a second client needing its own file (then design a
          general delivery-verification mechanism instead of a third special
          case). Note the deeper unsolved problem: across 320 tool calls in the
          benchmark the agent never once called a slate_* tool, so delivery of
          the *prose* is fixed while the freshness signal itself still depends
          on an agent choosing to ask for it.
```

```
Date: 2026-07-27
Decision: Freshness is delivered to Claude Code as hook-injected context, not as
          an MCP tool the agent may call. `slate agent hooks install` (also run
          by `slate agent enable claude`, opt out with --no-hooks) writes two
          entries to `.claude/settings.json`: a SessionStart hook that states
          the whole layer's trust state, and a PreToolUse hook on
          Read|Edit|Write|NotebookEdit that warns only when the target file is
          covered by the watches of a non-fresh doc. New `slate/claudehook.py`;
          the handler is `slate agent hook`, reading the payload on stdin.
Rationale: The MCP path was measured and it does not work. Across 25 real
          headless sessions the agent made 0 calls to any slate_* tool in 320
          tool calls, while the server reported connected and AGENTS.md told it
          to check freshness first (benchmarks/agentbench/RESULTS.md). The
          entire freshness engine — the product thesis — went unexercised by
          every session that had it. A signal the model must opt into competes
          with grep, and grep wins: cheaper, and it always returns something.
          Hooks are not offered to the model, so there is no choice to decline.
Evidence:  Verified end-to-end, not assumed. In a real repo with two
          deliberately stale docs, a headless session answered which docs were
          untrustworthy — naming both docs, their claim counts, the anchor
          commit and the culprit file — in one turn with zero tool calls. The
          PreToolUse warning was reproduced verbatim by the model at the moment
          it read a covered file. Project `.claude/settings.json` hooks DO fire
          under `claude -p`, unlike `.mcp.json`, which needs --mcp-config; that
          asymmetry is why this delivery path works headless and the MCP one
          did not.
Trade-off: ~380ms per PreToolUse evaluation (a repo scan plus a git diff; only
          ~57ms is interpreter start). Deliberately uncached: a cache in the
          warning path is a mechanism for suppressing a warning that should
          have fired, which is the one failure §10 forbids, and 380ms sits
          inside the noise of a tool-call round trip. Revisit only with a
          measurement showing it hurts. Second trade-off: this is a third
          Claude-specific artifact after CLAUDE.md and .mcp.json, sharpening
          the precedent the previous entry flagged.
Safety:    The hook computes no trust math — it calls freshness.evaluate_all and
          renders, exactly as cli and mcp do, so there is no second
          implementation of "is this doc fresh" to disagree with the first.
          Every entry point is wrapped: a malformed payload, a missing layer, a
          path outside the repo, or an internal exception all resolve to silence
          and exit 0. Nothing ever prints "fresh" for a doc it failed to
          evaluate. Verified that with `slate` absent from PATH the hook fails
          and the session still completes normally (is_error false) — the
          PATH assumption degrades to no signal, never to a broken session.
          PreToolUse stays silent on the context docs themselves, since editing
          a stale doc is the agent healing it. Pinned by
          tests/test_claude_hook.py (30 tests).
Revisit trigger: Evidence that the SessionStart text is being ignored the way
          the MCP tools were — delivery into the window is now proven, but
          whether it changes task outcomes is NOT measured. The 0/25-correct
          benchmark was not re-run against this delivery path; do not claim a
          task-level improvement until it is.
```

```
Date: 2026-07-27
Decision: Hook delivery ships, but the benchmark's claim about it is limited to
          "the signal now arrives". The cost effect measured alongside it is
          recorded as exploratory and must not be quoted as a demonstrated win.
Rationale: The sweep did what it was built to do — it falsified the hypothesis
          it was given. `decoy_hits` was pre-registered in spec.py as the metric
          hook delivery should move; it did not move (exact p=1.0) and went the
          wrong way (1/5 -> 2/5 trials). Reporting the cost effect that *did*
          appear as if it had been the hypothesis is precisely the move this
          repo has caught itself making before (the "28% token saving" that was
          two doc types on a turn-scaled metric).
Evidence:  slate-stale -> slate-stale-hooked: tool calls 41->31 (p=0.0159),
          turns 42->32 (p=0.0159), context 56.5K->41.5K (p=0.0079, the floor
          for n=5). slate-fresh -> slate-fresh-hooked: nothing (p=0.44-0.69).
          Effect present only where the layer is stale is the interaction the
          mechanism predicts and is not what a time-of-day or model-drift
          confound looks like — those move both arms. Exact two-sided
          Mann-Whitney by enumeration, written into report.py rather than
          imported, since the package has no runtime dependencies.
Trade-off: The three cost metrics are one behavioural change measured three
          ways, not three findings: cache-creation per turn is 1,344 vs 1,294,
          so tokens track turns track tool calls. Eight tests were run; strict
          Bonferroni puts the best result at the edge of significance. n=5.
Safety:    Correctness stayed 0/5 in every arm (0/35 cumulative), so nothing
          here supports a claim about accuracy. The report says so in its
          headline rather than in a footnote.
Revisit trigger: A replication that pre-registers cost at higher n, with
          SessionStart and PreToolUse as separate arms — the current sweep
          installed both together and cannot attribute the effect to either.
```

```
Date: 2026-07-27
Decision: `hook_injections` is documented as a floor on delivery, not a count
          of it, and the PreToolUse marker is recorded in spec.py as
          unobservable rather than dropped.
Rationale: The raw metric read "PreToolUse fired 0 times in 10 trials", which
          would have been published as half the feature being dead. It is
          false. Claude Code writes SessionStart's injected context into the
          stream-json transcript but not PreToolUse's, so a warning that fired
          and reached the model leaves no trace to count.
Evidence:  Established by instrumenting the hook command itself to append every
          invocation to a log: a session that read a covered file logged both
          `SessionStart` and `PreToolUse Read`, each returning
          additionalContext, while the transcript for that same session
          contained only the SessionStart marker. The agent had read
          src/flask/ctx.py — the exact file the stale doc misdescribes and the
          one a manual probe warns on.
Trade-off: The sweep therefore cannot attribute its effect to SessionStart or
          PreToolUse. That is a real limit on the result and is stated in the
          report's threats-to-validity rather than left implicit.
Safety:    The general rule this is an instance of: a benchmark metric that can
          only observe part of the mechanism must say so at the point it is
          read, or the next person to read it will draw the confident wrong
          conclusion. Two other instruments were wrong in the same sweep —
          `--reparse` let an older sweep's transcript overwrite a newer one's
          metrics, and run provenance was dated by a mtime that `--reparse`
          resets and a UTC conversion that merged two evenings into one day.
Revisit trigger: Claude Code recording PreToolUse additionalContext in the
          transcript, which would make the count exact and let the two hooks be
          told apart without separate arms.
```

```
Date: 2026-07-27
Decision: Generate co-change coupling from `git log` as a tracked fact — which
          files repeatedly change in the same commit — rendered into the
          architecture auto-block. New `slate/cochange.py`, a `cochange` field
          on `RepoScan`. Code files only, ranked by count x Jaccard, counts
          computed but never rendered.
Rationale: Every other generated fact describes the tree as it stands, and an
          agent rederives all of it in two or three tool calls. That is the
          benchmark's result, not a suspicion: a fresh Slate layer changed
          nothing an agent did (`slate-fresh` 59 turns vs `bare` 63, p=0.85;
          83.4K context vs 70.7K, p=0.09 — if anything worse), and so did a
          hand-written doc. Nothing in the layer was worth its own tokens
          because nothing in it was hard to look up. History is the exception:
          "what else moves when this moves" is in the log, not the tree, and
          across 15 measured sessions no agent ran `git log`, `git blame` or
          `git show` even once. It answers the question grep cannot — not
          "where is X" but "is my change complete".
Evidence:  On Flask, two of the three files the benchmark's task must touch
          surface as pairs in the top twelve, with `app.py`<->`helpers.py`
          first. On this repo it surfaces `cli.py`<->`mcp.py` — every
          capability is exposed twice, which is the fact a new contributor
          most needs and least expects. ~70ms on a 235-file repo.
Trade-off: Ranking is the whole feature and both obvious measures fail, in
          opposite directions, as measured on Flask rather than reasoned
          about. Raw count ranks hub files first: six of twelve slots went to
          `CHANGES.rst` paired with whatever a commit happened to touch, and
          the useful pair was pushed out. Jaccard alone ranks rare files
          first: two docs edited three times, always together, outranked a
          pair that co-changed twelve times, evicting the ground truth
          entirely. `count x jaccard` requires both frequency and specificity.
          Restricting to code files is the other half — changelog and CI
          coupling is real but is release hygiene, and 13 of 15 sessions found
          `CHANGES.rst` unaided anyway.
Safety:    Counts are computed and deliberately not rendered. A count changes
          on nearly every commit touching two watched files, which would leave
          architecture.md permanently stale and teach the reader to ignore the
          staleness signal — losing the product's core claim to display a
          number. Pairs are selected by strength and rendered alphabetically,
          so the block moves only when set membership moves. Bulk commits
          (>25 files) are excluded or a reformat would assert coupling between
          every pair it swept up; the context layer is excluded or `slate
          sync` — which rewrites every generated doc in one commit — wins
          every slot in every Slate repo. Output is fully sorted and pinned
          byte-identical across PYTHONHASHSEED, since a fact that renders
          differently run to run manufactures a false `stale`. Every failure
          path (no history, shallow clone, missing git) yields no facts rather
          than breaking the scan. tests/test_cochange.py (16 tests) pins the
          two ranking failures above as regressions.
Revisit trigger: A measurement showing whether this changes agent behaviour.
          It is motivated by a measured blind spot, but is itself unmeasured —
          the benchmark cannot currently test it, since `bare` already scores
          6/6 on the revised task. `found_target_after` is the metric to watch
          once a task with headroom exists.
```

```
Date: 2026-07-28
Decision: Co-change facts default OFF (`SLATE_COCHANGE=1` opts in). The code,
          the hook injection and all 25 tests stay; nothing ships enabled.
Rationale: The idea passed every check except the one that counts. Facts are
          correct, deterministic, ~70ms, and name exactly the file the
          benchmark's agents miss. Both deliveries were then measured against
          `bare` on revision 3, 6 trials each, and both failed:
            rendered in the doc  — the layer named app.py <-> sessions.py and
                                   every trial missed sessions.py anyway; the
                                   two trials that opened architecture.md
                                   scored *worse* on scope than those that did
                                   not. correct 0/6 vs 0/6, all p > 0.13.
            injected at the edit — hook fired 6/6 (proved by the cochange-seen
                                   artifact), named sessions.py in 3/6, and 0
                                   of those 3 edited it. correct 0/6 vs 0/6,
                                   ground_truth_edited 3.0 -> 2.0 (worse),
                                   context 41,068 -> 59,816 (p=0.0411).
Evidence:  The cross-tab is the finding. Told about sessions.py and edited it:
          0. Told and did not: 3. Never told: 3. Not a delivery failure — the
          artifact proves the hook ran. Not a wrong fact — it named the file
          with a co-change count. Not Slate-blindness — the same sessions
          obeyed Slate's instruction to update decisions.md and read-next.md.
          The other 3 expose a limit no tuning fixes: the hook is reactive to
          the agent's entry point, and those trials entered via ctx.py, whose
          partners do not include sessions.py.
Trade-off: Shipping it on would charge every session 46% more context
          (p=0.0411 — the only significant result in the sweep, and against
          us) for a fact measured twice and moved nothing. Off by default is
          the honest position; deleting it would throw away a clean negative
          and a reusable instrument.
Safety:    Gated at all three call sites (scanner computes nothing, generator
          omits the section rather than rendering it empty, hook returns
          early). `test_scan_omits_cochange_by_default` and
          `test_cochange_is_off_without_the_opt_in` pin the default so it
          cannot drift back on unnoticed; the feature tests opt in explicitly
          rather than passing for the wrong reason.
Revisit trigger: A task shape where coupling is genuinely undiscoverable —
          a larger repo, a weaker agent, or a change whose second file shares
          no vocabulary with the first. This task is not that: the agents
          reached 3 of 4 ground-truth files unaided. Do not re-enable without
          a measurement; the prior is now that agents do not act on
          completeness advice regardless of how it is delivered.
```

```
Date: 2026-07-30
Decision: `read-next.md` is watch-based like the generated docs; `decisions.md`
          stays attestation-based. `context.default_watches` no longer returns
          [] for both.
Rationale: Measured over all 54 commits of this repo's history, *zero* human
          claims were ever evaluated — not "none were stale", none were
          checked. The claim-bearing docs (read-next: 11 claims, decisions: 7)
          carried no watches, and `_evaluate` returns FRESH before reading the
          body when the watch list is empty; the watched docs carry no prose
          refs at all. The two sets were disjoint, so Part B's human half had
          never executed. Re-walking history with watches injected surfaced
          real rot: read-next claimed "top-level-dir granularity only — no
          resolver" for 4 commits after `da71aae` made the map package-level
          and added a resolver.
Trade-off: read-next now goes stale on most code commits, and `slate sync`
          cannot clear it — it has no auto-block, so only `slate mark` (after
          a human or agent actually updates the focus text) re-anchors it.
          That is the intended workflow, but it does put the CI gate in the
          path of every PR that touches slate/ without updating the focus.
Safety:    `decisions.md` is deliberately left attested: it is append-only and
          a past decision stays true as a statement about the past.
Revisit trigger: Alarm fatigue — if read-next is marked without being read.

Date: 2026-07-30
Decision: Freshness narrows on authorship: a claim whose prose was written at
          or after the change to the code it names is fresh
          (`freshness._prose_supersedes`, `gitutil.blame_lines` /
          `is_ancestor` / `last_change_commit`). Both ref kinds: a symbol ref
          resolves through `_symbol_files` to the changed code files that
          could host it, widening to *every* changed code file when the
          qualifier is unresolvable, so prose must outdate all of them.
Rationale: Prose and code that land in the same commit are not doc rot — the
          author wrote the sentence against the change — but the doc's anchor
          predates that commit, so the claim was flagged the moment it was
          written. On the corpus above this was 6 of 31 flags (19%), and it
          was the single largest false-positive class. Both arms measured
          through identical code paths with only the narrowing toggled:
          31 -> 25 hit-instances. Symbol coverage changes nothing historically
          (those flags are genuinely older than their code) but took this
          repo's live working tree from 8 suspect claims to 4.
Trade-off: ~500ms vs ~406ms unnarrowed on this repo (23%). Naive per-claim
          blame cost 78%; the fixes are whole-doc blame (`blame_lines`) and a
          per-evaluation answer cache (`_GIT_ANSWERS`), cleared at the top of
          `evaluate_all`/`evaluate_doc` so a long-lived MCP process cannot
          serve an answer from a previous repo state.
Safety:    Narrowing only, exactly like symbol resolution: every unanswerable
          question (no blame, unresolvable anchor, missing file) returns False
          and leaves the verdict alone, so it can never manufacture a `fresh`.
          Pinned by `test_narrowing_declines_when_blame_cannot_answer` and
          `test_prose_older_than_the_code_change_stays_stale`.
Note:      `_claims_still_check_out` returned False outright for any doc with
          `generated: false`. Dead while such docs were unwatched; once
          read-next was watched it made the doc permanently stale regardless
          of its claims. Non-generated docs now skip only the auto-block
          conditions and are judged on their prose refs.
Revisit trigger: Path refs remain the residual over-flag — a file changing
          after a sentence was written puts it at risk without falsifying it.
          The fix is a prose convention (name `module.symbol`, not
          `path/to/file.py`), which Part A already narrows for free, not more
          trust math. Known bound: a claim is blamed as a unit, so an old
          paragraph that gains a new ref blames to its oldest line and stays
          flagged. Blaming only the ref's own line would be more precise;
          it is also the less conservative direction, so it waits for a
          measured need.
```

```
Date: 2026-07-31
Decision: Repair tasks are a read-only worklist (`slate/repair.py`,
          `slate repair [--json]`), and they cover hand-written claims only.
          `ClaimVerdict` gained `doc_path`/`line`/`end_line`/`scope`;
          `freshness._symbol_files` became public `symbol_files` so repair can
          resolve a symbol ref to its candidate files without forking the
          logic.
Rationale: The pivot needs an addressable unit before it can need anything
          else, and the read-only half is also the instrument for the Phase 0
          experiment that gates the rest: a formatted task is exactly what you
          hand an agent. Generated facts are excluded because `slate sync`
          already rewrites them deterministically for zero tokens — and over
          this repo's entire history, generated drift was the *only* staleness
          that ever occurred, so routing it to a model would be strictly worse
          than the machinery that already fixes it.
Trade-off: `scope` exposes how strong the evidence is — `symbol` (the named
          symbol provably moved) versus `path` (a file changed somewhere) —
          because on the measured corpus most path-scoped flags were prose
          that was still accurate. A consumer that cannot answer "this claim
          is still correct" will rewrite correct prose on the common case.
          That constraint propagates to Phase 2: the verification gate must
          accept "no change needed" as a verifiable outcome, not only "the
          claim now checks out".
Safety:    Computes no trust and writes nothing. It reads `freshness`'s
          verdicts, exactly as `cli`, `mcp` and `claudehook` do; a second
          opinion about whether a doc is fresh is a second thing that can
          disagree. New `ClaimVerdict` fields are additive, so status/verify/
          diff and the MCP surface are unchanged
          (`test_claim_verdicts_stay_backward_compatible`).
Revisit trigger: Phase 0's exit criterion — hand an agent a task, does the
          rewrite make Slate's own verifier turn it fresh, >=60% with ~0%
          wrong-but-verifying. It has never been run. If it fails, the write
          path in Phase 2 and 3 should not be built at all, and this module
          stays what it is today: a list for a human.
```

```
Date: 2026-07-31
Decision: The repair experiment's original exit criterion — "an agent's rewrite
          makes Slate's own verifier turn the claim fresh" — is retired as
          circular and must not be revived. Replaced by three pre-registered
          thresholds in `benchmarks/repairbench/spec.py`, over two balanced
          arms of 18 claims frozen beside it.
Rationale: Authorship narrowing (`freshness._prose_supersedes`) clears a claim
          whose prose is newer than the code it names, and a repair is newer
          prose by definition — committed or not. Freshness therefore reads a
          timestamp the repair itself just updated. Measured directly:
          replacing a stale sentence with "`engine.run` returns 9999 purple"
          turns the doc fresh. The criterion would have scored ~100% for an
          agent writing garbage.
Trade-off: None of the replacements measure truth, because no deterministic
          check reaches it. They measure the two ways a repair is actively
          worse than the staleness it replaces: naming code that does not
          exist (>=90% of rewrites must fully resolve), and naming no code at
          all (>=95% must keep refs — `claims._emit` drops a claim with no
          refs, so stripping backticks makes a sentence permanently
          uncheckable). Correctness is adjudicated by hand afterwards.
Safety:    The control arm is the load-bearing one. Phase 0.5 measured that
          most claims Slate flags are prose that is still accurate, so the
          experiment includes 18 claims the maintainer saw and deliberately
          left alone; the agent must decline on >=50% of them. An agent that
          rewrites whatever it is shown damages docs rather than repairing
          them, and skill on the treatment arm does not compensate. The prompt
          is identical across arms and never asserts that a sentence is stale.
Note:      This also condemns the plan's Phase 2 gate as drafted, which
          required "the target claim becomes fresh". That gate would accept
          nonsense from every trial. The shape survives — the agent proposes,
          a deterministic check decides — but the check has to rest on signals
          the repair cannot move by existing.
Revisit trigger: Failing any one threshold means Phases 2 and 3 are not built
          and `slate repair` stays a read-only list for a human. Passing all
          three is a floor, not a licence: it says the agent does not make
          things worse, not that it makes them right.
```

```
Date: 2026-07-31
Decision: Symbol references resolve by dotted *module path*, not by filename
          stem. `_changed_symbols` carries `_module_path(hit)`
          (`src/flask/views.py` -> `flask.views`, `pkg/__init__.py` -> `pkg`)
          and `_symbol_verdict` matches a ref's qualifier — or its full dotted
          prefix — through `_qualifies`.
Rationale: Stem matching produced a false `fresh`, the one failure §10 forbids.
          A claim about `pkg.request` whose symbol lives in `pkg/__init__.py`
          never matched, because that file's stem is `__init__`; and when any
          unrelated `fixtures/pkg.py` existed the qualifier counted as "known",
          which suppressed the conservative fallback that would otherwise have
          caught it. Flask has exactly that shape, a test fixture named
          `flask.py` beside the real package, which is how repairbench found
          it: 9 of 18 corpus pairs carried evidence resolved to the wrong file.
Trade-off: `_qualifies` matches a bare tail as well as a dotted prefix, so
          `views` still names `flask.views` and an unrelated `a.b.views` also
          matches. Deliberately generous: matching too much costs a false
          `stale`, matching too little costs a false `fresh`, and only one of
          those is allowed to happen.
Safety:    Three tests, one per direction — the decoy case that was falsely
          fresh, a `src/` layout that stem matching could not reach at all, and
          an unrelated-module edit that must stay fresh so the broader matching
          cannot be paid for in alarm fatigue.
Revisit trigger: The remaining half of the problem is untouched — `refs`
          assumes every backticked dotted name is code in *this* repo, so
          `logging.Formatter` matches a local `logging.py`. Any doc citing
          stdlib or a third-party API gets false staleness, and no repairbench
          corpus is trustworthy until that is fixed.
```

```
Date: 2026-07-31
Decision: Do not disambiguate stdlib references with `sys.stdlib_module_names`.
          A doc citing code outside this repo keeps whatever verdict symbol
          resolution reaches, including a conservative one.
Rationale: This was recorded as the next blocker and the record was wrong. It
          was measured before being built: module-path resolution had already
          closed the common case. A doc citing stdlib `logging.Formatter` in a
          repo with its own `app/logging.py` stays fresh when that module
          changes, because resolution sees the module never defined
          `Formatter`. Only two cases remain — an unparseable local module
          (`unknowable`) and a local module that genuinely defines the same
          name (`stale`) — and both are ambiguity, not error.
Trade-off: Those two cases are false positives for a doc that meant the
          standard library, and they stay. Clearing them means treating a
          stdlib-rooted name as external, which would stop flagging a doc that
          writes `logging.Formatter` about its *own* module. That is a false
          `fresh` traded for a false `stale`, and only one of those is
          permitted (§10).
Safety:    All three behaviours pinned in `tests/test_freshness.py` — the
          fresh case, the unparseable case, and the shadowing case — so a
          later "cleanup" cannot quietly convert them.
Revisit trigger: A real repo where stdlib citations produce enough noise to be
          worth the risk, *and* a way to tell "the doc means the stdlib" from
          "the doc means our module of the same name" that does not rest on
          the name alone. Import analysis of the documented module would do
          it; a name list would not.
```

```
Date: 2026-08-01
Decision: repairbench ground truth is *constructed*, not mined. `corpus.py`'s
          `build_trial` checks out a real Flask commit's parent, runs `slate
          init`, commits an authored passage, and applies the `src/` half of
          that commit on top. The corpus is 12 falsified passages and 12 the
          commit leaves true.
Rationale: Three cycles of mining real history failed the same way — the
          evidence attached to a sentence was inferred by ref resolution, and
          it was wrong for 9 of rev 1's 18 pairs. Each resolver fix narrowed
          that without solving corpus scale. Constructing inverts it: the
          passage's truth value is known because it was chosen, and the
          falsifying diff is known because it was applied. rev 3 measured 12/12
          vs 0/12 across arms (p=3.7e-07), the discrimination rev 1 could not
          see at all when both its arms declined at ~88%.
Trade-off: The passages are authored for the experiment, so they are cleaner
          than prose someone wrote for its own sake, and one of the 12 still
          carried a mis-authored `old_fact` — construction reduces mislabelling
          (13 of 18 -> 1 of 12) without eliminating it. Authoring a passage
          does not guarantee you understood the commit.
Safety:    `corpus.py --verify` gates every item before a run: Slate must raise
          exactly one task for the passage and its evidence must name exactly
          the applied commit. The prose commit must precede the code commit or
          `freshness._prose_supersedes` narrows the item out of the experiment,
          and only the `src/` half is applied because `CHANGES.rst` entries
          exist in the falsified arm only.
Revisit trigger: A second subject repo. Flask has clean, single-purpose
          commits; a repo that lands five things at once may not admit a
          passage with one known truth value.
```

```
Date: 2026-08-01
Decision: When a benchmark's instrument is wrong, bump `spec.REVISION`, fix it,
          and run fresh sessions. Never re-score recorded text, and never move
          a threshold to meet a result.
Rationale: rev 2 failed repair quality at 45%, and all six shortfalls were
          correct repairs the scorer misread — four of them prose that named the
          old behaviour in order to retire it. The tempting move was to re-score
          the stored text with a better matcher. That is choosing the metric
          after seeing the data, which is the exact failure this benchmark
          exists to avoid; the thresholds stayed where rev 2 set them and rev 3
          re-ran all 24.
Trade-off: Fresh sessions cost real money and hours, and rev 3 still shipped
          with two known scorer defects rather than a third re-run. Both are
          conservative — they cost the agent credit it earned — so the PASS
          survives them, and they are recorded in RESULTS.md rather than
          silently patched.
Safety:    Every record carries its `revision`; `run.py --report` only counts
          records matching `spec.REVISION`, so a stale sidecar cannot be mixed
          into a later run's numbers. Hand adjudication is stored beside the
          mechanical score in `results-rev3.json`, never merged into it.
Revisit trigger: An instrument defect that is *not* conservative — one that
          could inflate a result rather than deflate it. That cannot be left
          standing and must trigger a fresh revision immediately.
```
