# repairbench — revision 3

**24 trials, 2026-08-01, `claude-sonnet-5`. Verdict: PASS. Phase 0 of
`docs/repair-and-resume-plan.md` is answered, and Phases 2–3 are unblocked.**

Pre-registration: [`spec.py`](spec.py), committed in `2eb1da5` before any agent
ran. Corpus: [`corpus_rev2.json`](corpus_rev2.json), constructed and verified
before the run. Raw records: [`results-rev3.json`](results-rev3.json), one
sidecar and one transcript per trial in [`runs/`](runs).

| Metric | Result | Threshold | |
|---|---|---|---|
| discrimination (falsified − accurate edit rate) | 100% − 0% = **100pp** | ≥40pp | pass |
| significance of that gap | Fisher exact **p = 3.7e-07** | p < 0.05 | pass |
| repair quality | **10/12 = 83%** | ≥70% | pass |
| rewrite still names code | **12/12 = 100%** | ≥95% | pass |

## The result

**The agent rewrote 12 of 12 falsified passages and touched 0 of 12 accurate
ones.** Perfect separation, on passages that Slate flags identically and that
are mechanically indistinguishable from inside a trial.

This is the measurement revision 1 could not make. There, both arms declined at
~88%, so the control threshold passed while measuring nothing. The question was
never "does the agent decline?" — it was "can the agent tell the difference?",
and the answer at n=12 per arm is yes.

The control declines are reasoned, not reflexive. Each cites the specific nature
of the change it was shown:

> c08: "a pure refactor — it fixes a Python compile-time restriction (no-arg
> `super()` inside a list comprehension) by hoisting `super().convert` into a
> local variable… The passage remains accurate."

> c07: "only the return type annotation changed from `FileSystemLoader | None`
> to `BaseLoader | None`, **which the passage doesn't reference**."

The second one matters more than it looks. The agent is reasoning about whether
the change intersects *what the sentence claims*, which is the judgement the
whole pivot depends on and the one `slate repair` explicitly cannot make.

## Adjudication (2026-08-01, by hand)

Every rewrite was read against the code it describes. **All 24 trials took the
correct action: 12 truthful repairs, 12 correct declines.**

The mechanical score says 10/12 on repair quality. Both shortfalls are
instrument defects, and both cost the agent credit it had earned:

- **`t04` — scorer error.** The rewrite names `__init_subclass__` correctly, and
  ends "(no longer a separate `MethodViewType` metaclass)". That trailing
  contrast put a negation cue inside the window around the *new* fact, so
  `states_new_fact` read False. Negation-awareness — added at this revision to
  stop punishing prose that retires a fact — belongs to the old-fact question
  only. Applied to the new fact, it penalises exactly the well-written contrast
  it was built to reward.
- **`t08` — corpus error.** The authored `truth` note claimed the subdomain is
  now derived from `SERVER_NAME`. It is not. The commit gates the
  `default_subdomain` branch on `host_matching` and changes its fallback from
  `None` to `""`. The agent's rewrite says exactly that and is more precise than
  the note it was scored against; `drops_old_fact` read False because it kept a
  clause the commit never falsified.

**Neither defect can have manufactured the PASS** — both push the score down.
83% is a floor on repair quality at this revision, not an estimate.

The corpus error is worth stating plainly: constructing ground truth reduced
mislabelling from 13 of 18 pairs in revision 1 to 1 of 12 here, but it did not
eliminate it. Authoring a passage does not guarantee you understood the commit.

## Neither defect was fixed and rescored, on purpose

Both fixes are known and neither was applied. Rescoring recorded text with a
matcher built after reading that text is choosing the metric to fit the result,
which is the failure this whole benchmark exists to avoid. A revision 4 that
fixes the scorer must run fresh sessions, and there is no reason to spend them:
the corrected number moves 83% → 100% on a threshold of 70% that already passed.

The fixes, for whoever does bump the revision:

1. `corpus.asserts()` should take the negation check as a parameter — on for
   `old_fact`, off for `new_fact`.
2. `t08`'s `old_fact` should name the unconditional "always uses" and the
   `None` fallback, which is what the commit actually falsified.

## Method

Ground truth is **constructed, not discovered** — the change that closed out
revision 1's failure mode. For each item, [`corpus.py`](corpus.py):

1. checks out `<commit>^`,
2. runs `slate init`, so the layer is generated and anchored there,
3. appends an authored passage to `.slate/read-next.md` and commits it,
4. applies the `src/` half of `<commit>` on top and commits that.

The passage's truth value at HEAD is known because it was chosen; the falsifying
diff is known because it was applied. No resolver stands between a sentence and
its evidence, which is what destroyed 9 of revision 1's 18 pairs.

Three construction details carry real weight:

- **Step 3 precedes step 4.** Prose committed *after* its code is narrowed to
  fresh by `freshness._prose_supersedes` — correctly — and would have dropped
  silently out of the experiment.
- **Only the `src/` half is applied, in both arms.** The full commits carry
  `CHANGES.rst` entries and only the falsified arm's commits do, so applying
  them whole would hand the agent an answer key that exists in one arm only.
- **All 24 are verified before the run** (`corpus.py --verify`): Slate raises
  exactly one task for the passage, and its evidence names exactly the applied
  commit. All 24 came back `scope: symbol`.

The prompt is identical across arms and says a passage "may be out of date",
never that it is (`spec.PROMPT_MUST_NOT_ASSERT_STALENESS`).

## What this does not show

- **Nothing about delivery.** Every trial handed the agent a scoped task and
  asked for a decision. That is not evidence an agent will repair docs it was
  not asked about — revision 1's clearest surviving finding, and the 2026-07-27
  sweep's, is that *offering* a documentation action does not get the action.
- **Nothing about unscoped repair.** The unit was one passage with one diff.
  "Repair the layer" is a different, larger task.
- **One model, one repo, n=12 per arm.** Flask is a well-documented library with
  clean commits. A repo with tangled commits is untested.
- **`refs_resolve` remains descriptive** and remains low (4 of 14 symbols in
  rewrites resolve). It is not a gate at any revision: it cannot express
  deletions, and prose about removed API is correct prose. See `spec.py`.
- **Wall clock is not model effort.** Median trial 15s, but six trials — three
  per arm — ran 15–65 minutes on API retries and backoff, and `c04`'s session
  dropped mid-response and was re-run (`5c59d69` makes a failed session void
  rather than scoring it a decline, so a dropped connection cannot look like
  discrimination). Total 4.7h for 24 trials is transport, not thinking.

## Revision history

**Revision 1 (2026-07-31) — void, inconclusive.** 36 trials, mined corpus,
`spec.verdict()` FAIL. The primary metric scored unchanged text (the agent
declined 16 of 18), the resolver could not express Flask's package-attribute
API, and it punished accurate prose about deletions. Hand-adjudication then
found 8 of 18 treatment pairs were editorial rewrites of true sentences and 9 of
18 carried misattributed evidence, leaving 5 usable pairs. The control arm ran
at n=8 because the corpus stored segmenter-normalised text that no longer
matched the file byte-for-byte. **Its primary number must not be quoted.**

What still stands from it: the agent never stripped backticks (18/18), and
agents mostly decline documentation actions they are merely offered.

**Revision 2 (2026-08-01) — superseded, not re-scored.** First run on the
constructed corpus. Discrimination passed decisively (11/12 vs 0/12; the one
falsified passage left alone was `t08`, the item whose ground truth is now known
to have been mis-authored). Repair quality failed at 45% — and all six
shortfalls, read by hand, were correct repairs the scorer misread: four negated
the old behaviour in order to retire it ("it no longer falls back to
`SERVER_NAME`"), and two `old_fact` patterns named details the commit never
removed. The scorer was made negation-aware, two corpus patterns were corrected,
**the thresholds were left exactly where they were**, and the revision was
bumped so nothing is compared across the change. Records:
[`results-rev2.json`](results-rev2.json).

**Revision 3 (2026-08-01) — this run.** Fresh sessions, 24/24 recorded.

## What it unblocks

Under the pre-registration, PASS means Phases 2 and 3 of
`docs/repair-and-resume-plan.md` get built. Two constraints the data puts on
Phase 2's verification gate:

1. **The gate cannot be freshness** (revision 1, still binding — a repair is
   newer prose by definition) and **cannot be `refs_resolve`** (it cannot say
   "gone"). Both are now measured dead ends, not suspicions.
2. **"No change needed" must be an accepted, verifiable outcome.** It was the
   correct answer in 12 of 24 trials here, and on real history most flagged
   claims are prose that is still accurate. A gate that only recognises
   successful rewrites scores the correct action as a failure.
