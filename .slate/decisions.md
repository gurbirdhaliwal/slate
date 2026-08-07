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

```
Date: 2026-08-01
Decision: `repair.verify_repair(before, after, target)` is a pure function of
          two document bodies and the segmenter. It returns `repaired`,
          `unchanged` or `rejected`, and it decides whether an edit is
          admissible — never whether the doc is fresh. The drafted
          `(root, doc, before, after)` signature was cut down.
Rationale: No check that survived Phase 0 needs the tree. Freshness cannot
          score a repair (a repair is newer prose by definition, so authorship
          narrowing reads a timestamp the repair just updated), and
          "every named symbol resolves" cannot express deletion — repairbench
          rev 3 measured 4 of 14 symbols in *correct* rewrites failing to
          resolve. What is left is textual: the claim still exists carrying
          refs, nothing else moved, and declining is a pass. A handle to the
          repo that no check uses is how a purely textual gate grows a second
          opinion about trust, which §10 forbids.
Trade-off: The gate cannot say a repair is *true*. `repaired` means well-formed
          and confined, nothing more. Truth stays with the human reviewing a
          proposal, and Phase 3 keeps repairs as proposals for that reason.
Safety:    `test_repair_cannot_manufacture_fresh` demonstrates the trap rather
          than assuming it — it asserts the doc really does turn `fresh` once
          the refs are stripped, then that the gate refuses the edit. Nine more
          adversarial cases cover ref deletion, unverifiable prose, collateral
          edits, editing the wrong claim, and relocation to another section.
Revisit trigger: A repair that legitimately needs to touch two claims at once
          (splitting a paragraph that documents two symbols). Today that is a
          rejection, deliberately — the safe direction — and a human unblocks it.
```

```
Date: 2026-08-01
Decision: The repaired claim is located by *section*, not by line number, and
          "no change needed" is an accepted outcome rather than a failure to
          repair.
Rationale: A rewrite reflows the paragraph it replaces, so pinning an exact
          line would reject the ordinary case; the segmenter already joins a
          unit's lines before emitting it, so re-wrapping is not a claim-level
          change at all. And declining was the correct action in 12 of
          repairbench rev 3's 24 trials — on real history most flagged claims
          are prose that is still accurate, because a `path`-scoped verdict
          only says a file changed somewhere near them.
Trade-off: Section granularity lets a repair move within its own section
          unnoticed. That is a smaller risk than rejecting every reflow, and
          the claim must still exist and still carry refs either way.
Safety:    `test_moving_the_repair_to_another_section_is_rejected` and
          `test_rewrapping_the_same_claim_is_not_an_edit` pin both sides.
Revisit trigger: A doc whose sections are large enough that "somewhere in this
          section" stops being a useful location.
```

```
Date: 2026-08-01
Decision: The end-of-session repair prompt is delivered on the `Stop` hook, not
          `SessionEnd`, with two independent loop brakes and no `decision:
          "block"` on any path.
Rationale: The plan drafted "SessionEnd/Stop ... additionalContext only", and
          half of that is impossible. A canary against a real session showed
          `SessionEnd` has no decision control and no `additionalContext` at
          all — it fires after the session is over and shows stderr to the
          user, so nothing it emits reaches the model. `Stop` accepts
          `additionalContext` and continues the conversation, which is the only
          place an end-of-session job can still be acted on.
Trade-off: Continuing the conversation is a loop by construction. It is bounded
          by `stop_hook_active` (observed False then True across one continued
          turn) and, independently, by a per-session note through
          `_already_announced` — so a client that drops the field still gets
          one announcement. Blocking would be stronger delivery and is refused:
          a hook that can prevent a session ending is the landmine this module
          was built around.
Safety:    Eight tests in `tests/test_claude_hook.py` — silent by default,
          silent on one switch, silent when the layer is clean, silent under
          `stop_hook_active`, once per session, never emits `decision`, and
          malformed input stays silence.
Revisit trigger: A client that offers a lifecycle event which is both late in
          the turn and free of continuation semantics. That would drop the loop
          brakes entirely.
```

```
Date: 2026-08-01
Decision: Hook text offers, it never commands. `claudehook.session_end_text`
          names itself and the settings file it came from, reports what it
          observed, and states that leaving a claim alone is a correct outcome.
Rationale: The canary injected a bare imperative and the model identified it as
          a prompt-injection attempt and refused it — correctly, and that is
          the behaviour we want models to have. An instruction arriving from a
          subprocess has no more authority than any other untrusted text, so
          delivery that reads like a command is delivery that gets declined on
          principle rather than on merit. Attribution and description are what
          make it legible as the user's own tooling.
Trade-off: Softer phrasing is weaker delivery, and Phase 4 may find it too
          weak. That is a measurable question; writing a stronger imperative to
          win it would be optimising for compliance against a model that is
          right to resist.
Safety:    `test_stop_names_the_suspect_claim` asserts the "correct outcome"
          language is present, so a later tightening of the copy cannot quietly
          turn it into an order.
Revisit trigger: Phase 4 showing uptake near zero *and* transcripts showing the
          agent read the text and declined on grounds other than suspicion.
```

```
Date: 2026-08-01
Decision: `slate_repair_apply` writes the doc after `verify_repair` accepts it,
          rather than only proposing a diff — but behind four consents, and it
          never re-anchors.
Rationale: The plan said start with propose-diff. A proposal the agent renders
          for a human to paste back gives the agent no path to the doc, and
          Phase 4's primary metric is suspect-claim count at session end versus
          session start — which would then be zero by construction, measuring
          the harness rather than the pivot. The propose posture is preserved
          by consent instead of by impotence: repair off by default, full
          access required on top, the client's own per-call permission prompt,
          and the verifier refusing anything malformed.
Trade-off: An agent can now change tracked files. That is the risk the plan
          named ("an agent silently editing tracked files is how a tool gets
          uninstalled once"), and it is bounded by leaving the change unstaged
          and the doc un-re-anchored, so the layer does not vouch for the new
          text until a human runs `slate mark`.
Safety:    `tests/test_mcp.py` pins the tool hidden without both switches,
          denied when called anyway, writing nothing on a rejected rewrite or a
          missing target, and leaving `slate_synced_commit` untouched on a
          successful one.
Revisit trigger: Phase 4 data on rejection rate. A high rejection rate means
          the agent is producing edits the gate has to catch, and the answer
          then is propose-only after all.
```

```
Date: 2026-08-02
Decision: Phase 4's E3 sweep is reported VOID, not negative. The convergence
          and kill-criterion numbers stand in the write-up but license nothing
          until a re-run with a corrected delivery gate.
Rationale: `MIN_DELIVERY` asked what fraction of repair-on trials saw the Stop
          hook inject. It read 50%. But the hook is meant to be silent when the
          layer is clean, and all five silent trials had `suspect_claims_end`
          of 0 — the agent had already closed the jobs. Of the trials that
          still had a job when Stop fired, the hook injected in 5 of 5. The
          gate could not tell "broken" from "nothing to say", which is my
          specification error, not a product failure.
Trade-off: The corrected reading is stated in E3-RESULTS.md and clearly marked
          post-hoc. Filing "delivery 50%" unexplained would be more misleading
          than explaining it; declaring PASS on a gate rewritten after it
          failed would be worse than either.
Safety:    The quantity needed for the corrected gate was already recorded
          during the run, so a revision 2 needs no new judgement — only fresh
          sessions, because a gate rewritten after seeing the data it failed is
          not a gate.
Revisit trigger: A re-run at E3 revision 2 measuring delivery against trials
          that still had a suspect claim at Stop time.
```

```
Date: 2026-08-02
Decision: `slate mark` is an ungated door into the trust layer, and it is
          recorded as such rather than closed mid-experiment.
Rationale: Phase 2's `repair.verify_repair` stops a repair manufacturing a
          false `fresh` — but it governs the MCP path only. Every one of the
          E3 control's convergences went around it: edit `read-next.md` with
          the ordinary Edit tool, then run `slate mark` in a shell. An agent
          with shell access needs neither `slate_repair_apply` nor full MCP
          access to re-stamp a doc's anchor, and `slate mark` verifies nothing
          about whether the prose is still true.
Trade-off: `slate mark` is the documented, intended command for a human who
          has actually reviewed a doc; the landmine about marking a doc you
          have not read has been in read-next since the layer was built. What
          is new is that an agent will now do it unprompted — 5 of 10 control
          trials did. Making `mark` refuse when claims disappeared would help
          the agent case and annoy the human one.
Safety:    Measured, not inferred: `direct_doc_edits` and the Bash-route
          `reanchor_calls` were added to the harness after the first metric
          reported zero for a trial that had plainly re-anchored.
Revisit trigger: Deciding whether `slate mark` should refuse to re-anchor when
          the claim count dropped since the last anchor — the same guard
          `verify_repair` applies, at the other door.
```

```
Date: 2026-08-02
Decision: Convergence of the context layer is bought by attestation, not by
          repair, and the repair loop's measured effect is on whether the agent
          touches the docs at all.
Rationale: Calling a re-anchor tool predicted convergence perfectly in both E3
          arms: the 5 control trials that called one closed 11 of 11 jobs, the
          5 that did not closed 0 of 5, and all 10 repair-on trials called one
          and closed 14 of 14. The switch doubled the rate of doing anything
          (10/10 vs 5/10, Fisher one-sided p=0.0163) — the same shape as the
          2026-07-27 finding that offering an action gets 3 calls in 687 while
          injecting it reaches every session. But only 7 of the treatment's 14
          closures went through `slate_repair_apply`; the other 7 took the
          control's unverified route.
Trade-off: The honest pitch is therefore not "repair converges the layer" —
          the layer often converges anyway. It is that the repair loop makes
          convergence *verified* rather than asserted, and that is a narrower
          claim than Phase 4 set out to test.
Safety:    Cost is recorded beside it: ~8 turns and ~12K context per session,
          with correctness 1/10 against the control's 2/10. Nothing here
          supports a correctness claim in either direction.
Revisit trigger: The re-run. If the gate route does not grow as a share of
          closures, the loop is an expensive way to prompt an attestation.
```

```
Date: 2026-08-02
Decision: Phase 4 passes at E3 revision 2, and the pitch it licenses is the
          narrow one: the layer converges either way, and repair makes about
          half of that convergence verified rather than asserted.
Rationale: All three pre-registered criteria cleared on fresh sessions —
          delivery 6/6 over the trials that still had a job when Stop fired,
          convergence 100% vs 36% (a 64pp gap against a 30pp bar), and 7
          verified repairs against 0 rejections. But the mechanism split
          replicated across both sweeps: 7 of 14 treatment closures went
          through `slate_repair_apply` in revision 1, 7 of 13 in revision 2.
          The rest were the agent tidying by hand, which is exactly what the
          control does when it converges at all.
Trade-off: The convergence *gap* should not be quoted precisely. The control is
          bimodal — it either tidies thoroughly or ignores the docs entirely —
          and its pooled rate swung 69% to 36% between identical designs. The
          direction is stable across two runs; the magnitude is not estimated
          well by either.
Safety:    Revision 1's records are archived under runs/e3-rev1/ rather than
          re-scored, and `e3_revision` stops the two measurements being
          averaged. MIN_DELIVERY and MIN_CONVERGENCE_GAP are pinned by a test
          so a later revision cannot move the bar while claiming to fix an
          instrument.
Revisit trigger: The share of closures going through the gate. At roughly half,
          the loop is partly an expensive way to prompt an attestation; if that
          share does not grow, the honest framing narrows further.
```

```
Date: 2026-08-02
Decision: A delivery gate measures "when there was something to say, did the
          hook say it" — never "did the hook say something".
Rationale: Revision 1 asked the second question, read 50%, and voided a sweep
          in which the hook had spoken every time it had anything to speak
          about. Slate's hooks are built to be silent when there is nothing to
          report, so a gate that counts silence as failure penalises the
          module for working. Revision 2 counts only trials that still had a
          suspect claim when Stop fired; the case the old gate could not see —
          silence *and* a claim left suspect — is the one that now fails it.
Trade-off: The denominator is inferred from the end-of-session count rather
          than observed at Stop time. The inference is tight, because the
          session is over when the count is taken, but it is an inference and
          is labelled as one.
Safety:    Both directions pinned in `tests/test_benchmark.py` —
          correct silence must not count against delivery, and a silent hook
          with work pending must still void the run — plus a test asserting the
          thresholds did not move when the denominator was corrected.
Revisit trigger: Any future gate on a component whose correct behaviour
          includes doing nothing. The same mistake is available every time.
```

```
Date: 2026-08-02
Decision: The value ledger counts repairs that passed the gate and repairs the
          gate refused. It does not count "sessions that started fresh because
          a prior session repaired them", which is what the plan asked for.
Rationale: That number is not available honestly. Phase 4 measured the
          counterfactual directly and it fails: a control with no repair loop
          converged its own layer in 36% of trials in one sweep and 69% in the
          other, by the agent rewriting the docs by hand. Crediting repair for
          a fresh session would claim something that happens anyway between a
          third and two thirds of the time. `refused` is the causally clean
          event — the edit did not land *because* the check said no, and there
          is no counterfactual to argue about.
Trade-off: The ledger therefore cannot show the compounding benefit the pivot
          was pitched on. That is the correct outcome of having measured it:
          the delayed benefit is real for the half that goes through the gate
          and unproven for the rest, and a ledger that implied otherwise would
          be the most damaging place in the product to overstate.
Safety:    `slate value` states the 36-69% control range inline, so the number
          cannot be read as "the layer stayed fresh because of Slate" without
          also reading what a layer does unattended. Pinned by a test.
Revisit trigger: A design that can attribute freshness to repair — a held-out
          arm where the same session is replayed with and without the loop.
```

```
Date: 2026-08-02
Decision: The docs reframe promised in Phase 5 ships as a *narrower* claim than
          the plan drafted. "Slate becomes a memory-consolidation layer" is not
          supported; "repair makes about half of the layer's convergence
          verified rather than asserted" is.
Rationale: The plan wrote the pitch before the experiment. Two sweeps put the
          control's unattended convergence at 36-69% and the treatment's
          gate-verified share at roughly half of its closures, so the
          consolidation framing would claim the whole of an effect that is
          partly the agent tidying up on its own. README now states the
          measured limits — including that no correctness effect was found in
          either direction, and that `verify_repair` guards the MCP path only.
Trade-off: It is a weaker headline than the pivot was launched on, and it is
          the one the evidence carries. Shipping the stronger version would
          have made the README the least reliable document in a repo whose
          entire product is document reliability.
Safety:    The README links E3-RESULTS.md at the point of the claim, so the
          number and its threats to validity travel together.
Revisit trigger: A sweep that isolates the gate route from the attestation
          route — if the verified share grows, the claim can grow with it.
```

```
Date: 2026-08-03
Decision: `slate mark` refuses to attest a doc that has fewer claims than at
          its last anchor. A human overrides with `--allow-claim-loss`; an
          agent cannot override at all.
Rationale: `repair.verify_repair` guards the MCP repair path, and the E3 sweep
          measured that agents reach a green layer through the other door —
          edit `read-next.md` with an ordinary file tool, then `slate mark`.
          Attestation is the one moment a doc's trust is renewed by assertion
          rather than evidence, so it is the one moment a deleted claim would
          never be noticed again. `repair.claim_loss` compares against the
          doc's content at its anchor via `gitutil.file_at_commit`.
Trade-off: Counted, not matched by text. A repair *changes* a claim's wording —
          that is what repairing is — so refusing on "this exact sentence is
          gone" would block every honest repair from being attested and make
          the guard a reason to stop using the feature it protects. The cost is
          that deleting claim A while adding unrelated claim B passes, which is
          the same bound `verify_repair` accepts.
Safety:    Six tests, including that a repaired claim still marks cleanly, that
          the human override works, and that an unanswerable comparison (no
          anchor, doc absent at the anchor) is not treated as loss so `mark`
          stays usable in a fresh repo. `slate_mark` and `slate_update_focus`
          both refuse over MCP; update_focus is the tool measured doing this.
Revisit trigger: A repo where legitimate claim deletion is frequent enough that
          the override becomes routine — at which point the guard is noise.
```

```
Date: 2026-08-03
Decision: Hook delivery is agent-agnostic via `slate/agenthooks.py`, which
          reuses `claudehook`'s renderers and varies only the envelope. Claude
          Code keeps its own entry point.
Rationale: What to say about freshness is not Claude-specific; only the
          lifecycle event, the config file and the JSON shape are. Codex turns
          out to be near drop-in — same event names, same stdin fields,
          `additionalContext` at the top level instead of nested. Claude keeps
          its own path because that one is canary-verified against a live
          session and pinned by 47 tests; routing it through a new adapter
          would trade measured behaviour for tidiness.
Trade-off: **Delivery is verified for Claude Code only.** Codex and Cursor are
          built from published contracts and have not been observed end to end,
          and Cursor's hooks are beta. `slate agent hooks install` says so at
          install time. Do not quote a Codex/Cursor install as delivery
          evidence the way the Claude sweep can be quoted.
Safety:    Cursor's `beforeReadFile` cannot inject context — it returns a
          permission decision only — so the file warning rides `preToolUse`,
          and Slate never sends a `permission` field on any path. Returning
          "allow" would let a freshness note widen the user's own permissions.
          Pinned by a test.
Revisit trigger: A canary run against real Codex and Cursor sessions. Until
          then the Claude path is the only one with evidence behind it.
```

```
Date: 2026-08-03
Decision: `cli.cmd_agent_hook` catches every exception itself, rather than
          relying on the handlers below it to be exception-proof.
Rationale: `claudehook.run` and `agenthooks.run` each swallow their own
          failures, which made the wrapper above them look like it did not need
          to. It did: a typo'd variable name raised a NameError before either
          handler was reached, and the client saw a crashing hook. The unit
          tests missed it because they call the handlers directly; an
          end-to-end run through the real CLI found it immediately.
Trade-off: A bare `except Exception: pass` at an entry point hides bugs from
          whoever is developing the hook. That is the correct trade here — the
          landmine is that a hook must never be the reason a session breaks,
          and losing one freshness note is strictly cheaper than a traceback.
Safety:    `test_the_cli_hook_entry_point_never_raises` drives the real CLI for
          every client against valid, malformed and empty payloads.
Revisit trigger: None. This is the module's oldest invariant.
```

```
Date: 2026-08-03
Decision: Record — do not try to close — the gap between "the code a claim
          names moved" and "the claim became untrue". Slate detects the first.
          Nothing in the product detects the second, and `repair.claim_loss`
          does not help because it counts claims rather than reading them.
Rationale: Found by walking into it. On 2026-08-03 this repo's `read-next` said
          porting the hooks to Codex and Cursor was "only worth porting once
          the effect replicates" *after* the port had shipped. Every reference
          in that paragraph still resolved, so `slate status` stayed green, the
          freshness engine had nothing to flag, and `slate mark` re-anchored
          the doc without complaint — attesting a sentence that had just been
          made false. The new `mark` guard did not fire either: no claim was
          deleted, one was simply contradicted.
Trade-off: Closing it means judging whether prose is *true*, which needs a model
          in the trust path. §10 and the whole repairbench arc say no: freshness
          cannot score a repair, a verifier that reasons is a verifier that can
          be wrong confidently, and the one failure this product forbids is a
          false `fresh`. A gap that is honestly documented is safer than a
          check that guesses.
Safety:    Written as a landmine in read-next, next to the existing warning
          that marking a doc you have not read turns the layer back into a
          rumor. That warning is now backed by an incident rather than a
          worry.
Revisit trigger: A deterministic signal for contradiction that does not require
          reading the prose — for example a claim that names a symbol whose
          *docstring* asserts the opposite. Narrow, but it would not need a
          model.
```

```
Date: 2026-08-03
Decision: When work lands whose stated precondition was never met, the record
          says so rather than quietly marking the item done.
Rationale: The carry-over list gated porting hooks to Codex/Cursor on "only
          worth porting once the effect replicates". The effect has not
          replicated; the port shipped on a direct instruction. That is a
          legitimate call by the person asking, and it is not the same thing as
          the sequencing having been satisfied. Silently ticking it off would
          leave a future reader believing a measurement exists that does not —
          the same failure as quoting a void sweep's numbers.
Trade-off: The list is noisier: it now carries why an item left it, not just
          that it did. Worth it in a repo whose product is document
          reliability.
Safety:    read-next names both items that left the list and distinguishes the
          one that was simply completed (the `mark` gate) from the one whose
          precondition was bypassed.
Revisit trigger: None. This is a documentation habit, not a mechanism.
```

```
Date: 2026-08-05
Decision: All file I/O in `slate/` declares `encoding="utf-8"`, pinned by a
          test that scans the source for unencoded `read_text`/`write_text`.
Rationale: `Path.read_text()`/`write_text()` without `encoding=` use the
          *locale* encoding — UTF-8 on Linux and macOS, typically cp1252 on
          Windows. Slate writes status glyphs (● ○ ◐ ✗), arrows (→ ↳) and
          verify bars (█ ░) into its own output and docs, and cp1252 cannot
          encode any of them. Demonstrated rather than assumed: encoding
          '● fresh ○ stale' as cp1252 raises UnicodeEncodeError. 43 call sites
          were affected.
Trade-off: None worth the name. The cost is verbosity at every call site.
Safety:    `tests/test_encoding.py` fails on any new unencoded call, and a
          second test asserts the glyphs really are outside cp1252 — so if
          Slate ever stops using them, the first test is revealed as no longer
          load-bearing rather than the bug being silently gone.
Revisit trigger: Python making UTF-8 the default everywhere (PEP 686). Until
          the minimum supported version has it, the explicit encoding stays.
```

```
Date: 2026-08-05
Decision: The Codex hook port is marked **unverified** rather than supported,
          and `slate agent hooks install` says so out loud. Cursor likewise.
Rationale: The canary failed. Against `codex-cli 0.137.0`, a repo with a stale
          layer and a Slate-written `.codex/hooks.json`, with the hook command
          tee'd on both ends, produced **zero invocations** — with hook trust
          bypassed and across three config shapes. The binary clearly
          implements hooks (`PreToolUse`, `SessionStart`,
          `HookHandlerConfig::Command`, `trusted_hash`, and a schema of
          `event`/`enabled`/`matcher`/`timeout`/`command`), so Slate is writing
          the wrong shape or to the wrong place. The published contract this
          was built from describes a map-of-events shape that this version does
          not appear to accept.
Trade-off: Shipping an installer that writes a config which silently does
          nothing is worse than shipping no installer, so the alternative was
          removal. The adapter is kept because the rendering and envelope logic
          are tested and correct, and the remaining work is one schema — but it
          must not be described as working until a canary says it does.
Safety:    `HookAgent.verified` is False for codex and cursor; install prints
          the negative canary result. README states it at the point of the
          claim.
Revisit trigger: The hooks schema for a specific Codex version, then the same
          canary re-run. The canary is the deliverable, not the config file.
```

```
Date: 2026-08-05
Decision: `benchmarks/RESULTS.md` is re-run rather than retired, and now leads
          with the fact that its headline ratio collapsed.
Rationale: The old file was stale (commit `a43a2f7`) and README linked it
          twice, so deleting it would have broken the docs. Re-running was
          cheap and deterministic — and the result is the finding: session-start
          advantage fell from 10.0x/26.5x to 2.0x/9.6x, not because Slate
          regressed but because *this repo's own layer bloated*. `read-next.md`
          is 34 KB and `decisions.md` is 74 KB against ~2 KB per generated doc,
          so "the smallest useful context" is now 28,210 tokens.
Trade-off: The headline number is far less flattering, and it is the true one.
          It also exposes that the ratio measures the layer owner's discipline
          as much as the tool.
Safety:    The caveat block sits above the tables, and README carries the same
          correction where it quotes them. The self-referential limitation is
          stated: for agent *behaviour* claims, agentbench is the file to read.
Revisit trigger: Nothing in Slate prunes the human-owned docs. If read-next
          keeps growing, the session-start cost keeps rising — a cap, or a
          `slate prune`, is the obvious follow-up.
```

```
Date: 2026-08-05
Decision: Fix the Codex output envelope to the nested
          `hookSpecificOutput.additionalContext` the spec requires, and keep
          `verified=False` because hooks still do not fire on the version
          tested.
Rationale: Two rounds of canary separated two different problems. Round 1 found
          a real bug — the envelope put `additionalContext` at the top level,
          taken from a summary rather than the spec, which would produce a hook
          that fires and whose output Codex ignores. Round 2 isolated the rest
          away from Slate: a minimal spec-shaped `hooks.json` with no Slate
          involvement, one `echo` appending to a file, also never fired. Tried
          repo-local and global locations, the `plugin_hooks` flag, and
          `enabled: true` at both levels, all with
          `--dangerously-bypass-hook-trust` confirmed active by its own warning.
          Zero invocations throughout. So the config Slate writes is not the
          problem; either `codex exec` does not run hooks or the feature is
          incomplete in 0.137.0 (0.146.1 is available).
Trade-off: The envelope fix is unverifiable end to end on this machine — it
          rests on the published contract, which is exactly the evidence
          standard that was wrong the first time. It is nonetheless strictly
          better than what it replaced, and a test pins the Codex and Claude
          envelopes as identical so they cannot drift apart again.
Safety:    `verified` records observation, not intent, and a test asserts only
          Claude is True. Nothing flips the others without a passing canary.
Revisit trigger: Upgrade Codex and re-run the isolation canary — the minimal
          no-Slate hook first, because if that does not fire nothing about
          Slate's config matters.
```

```
Date: 2026-08-05
Decision: Codex hooks are written to `~/.codex/hooks.json`, and Codex delivery
          is now canary-verified. Cursor stays unverified.
Rationale: The port failed for three different reasons, found in order. (1) The
          envelope was flattened — `additionalContext` at the top level rather
          than nested under `hookSpecificOutput` — which produces a hook that
          fires and whose output Codex discards. (2) On 0.137.0 nothing fired at
          all, and a minimal no-Slate hook did not fire either, which pointed
          away from Slate. (3) On 0.146.1 the minimal hook fired from
          `~/.codex/` but not from the repo. That was the real bug: Slate wrote
          `<repo>/.codex/hooks.json`, which Codex silently ignores. Proven
          rather than guessed — malformed JSON at the global path warns "failed
          to parse hooks config"; the identical file in a repo produces nothing.
          Re-run end to end: all three events fire and Slate's SessionStart
          freshness arrives correctly.
Trade-off: Codex's config is per-user, so unlike Claude's it cannot be committed
          and shared — each developer runs install once. It is also the only
          thing Slate writes outside the repo, which SECURITY.md now states.
Safety:    `HookAgent.verified` is True only for the two that were observed
          working, pinned by a test. Tests that touch Codex config redirect
          HOME, because the first run of that test edited the developer's real
          `~/.codex/hooks.json`.
Revisit trigger: Cursor, when a CLI is available to canary against.
```

```
Date: 2026-08-05
Decision: Do not parse file paths out of shell commands to make PreToolUse work
          on Codex.
Rationale: Codex reads files by running shell — the observed payload is
          `tool_name: "Bash"`, `tool_input: {"command": "sed -n '1,200p'
          demo/engine.py"}` — so there is no `file_path` and `_rel_target`
          correctly returns None. Recovering the path would mean parsing
          arbitrary shell, where a wrong guess produces a freshness warning
          about a file the agent never touched. A warning that fires on the
          wrong file is worse than no warning: it is the alarm-fatigue failure
          the PreToolUse design already goes out of its way to avoid.
Trade-off: The file-touch warning is effectively Claude-specific in practice.
          On Codex the working signals are SessionStart and Stop, and the
          install output says so rather than leaving the user to notice.
Revisit trigger: Codex exposing a structured read tool, or a hook payload
          carrying resolved paths alongside the command.
```

```
Date: 2026-08-07
Decision: Every `subprocess.run` under `slate/` pins
          `encoding="utf-8", errors="replace"`, and `_git` raises `GitError`
          rather than ever returning `None` stdout.
Rationale: `text=True` alone decodes with the *locale* codec. On Windows that
          is cp1252, so the first non-ASCII byte in a diff killed subprocess's
          reader thread; `run` then returned `stdout=None` and `_parse_hunks`
          crashed on it. The crash was the lucky outcome. An unreadable diff
          and an empty diff are the same value to everything downstream, and
          `freshness._changed_symbols` reads an empty hunk map as "no symbols
          changed" — which narrows stale→fresh. That is a false `fresh`
          manufactured by a decode that never happened, and §10 says the
          engine may never produce one. `errors="replace"` rather than
          `strict` because git emits file *content*, whose encoding is not
          ours to promise; a mangled character in a diff line costs at most a
          missed symbol match, and the conservative fallback is "assume
          stale".
Trade-off: A repo whose files are genuinely cp1252 gets replacement chars in
          the hunk text Slate parses. Symbol resolution can miss such a
          symbol and fall back to path-level "assume stale" — the safe
          direction. Not worth a per-repo encoding setting until someone has
          an actual non-UTF-8 repo.
Revisit trigger: A user with a legitimately non-UTF-8 codebase reporting
          over-broad staleness.
```
