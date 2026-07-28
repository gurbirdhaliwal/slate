---
slate_doc: decisions
slate_generated: false
slate_synced_commit: 286f0bb
slate_synced_at: 2026-07-28T17:30:17+00:00
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
