"""Pre-registered definition of the repair experiment.

Everything a skeptic would accuse us of tuning after the fact lives here and is
fixed before any agent runs: the corpus, the arms, the metrics, and the numbers
that decide whether the repair pivot proceeds. The harness only executes it.

The question
------------
Slate can name the sentence that went stale. The pivot in
``docs/repair-and-resume-plan.md`` proposes letting the user's own agent fix
that sentence and carry on. That is only worth building if an agent handed a
stale claim and the diff that broke it produces prose that is *better*, not
merely different — and, just as importantly, leaves alone the prose that is
still correct.

Why the freshness criterion was retired (revision 1, still binding)
------------------------------------------------------------------
The plan pre-registered "does Slate's own verifier turn the claim fresh, >=60%".
That criterion is dead and must not be revived. Authorship narrowing
(``freshness._prose_supersedes``) clears a claim whose prose is newer than the
code it names — and a repair is newer prose by definition, committed or not. So
freshness reads a timestamp the repair itself just updated. Measured directly:
replacing a stale sentence with "`engine.run` returns 9999 purple" turns the
doc **fresh**. ``fresh_after`` is still recorded here, and is still never a
criterion.

Why revision 1's replacement metrics were retired too
-----------------------------------------------------
Revision 1 gated on ``refs_resolve`` — every symbol the rewrite names must exist
in the tree. It failed at 29%, and the failure was the instrument's:

* it scored *unchanged text*, because the agent declined 16 of 18;
* Flask's API is package attributes (``flask.request``, ``flask.g``), which
  shallow resolution cannot express;
* it punishes accurate prose about deletions — "the ``flask.ext`` package has
  been removed" is true, useful, and names something that by definition no
  longer resolves.

The third is not an implementation bug. A gate that cannot say "gone" cannot
verify documentation about a codebase that deletes things, so ``refs_resolve``
is **descriptive only** at this revision and must not be revived as a gate.

Revision 1's control threshold was worse than useless: both arms declined at
~88%, the threshold passed, and it measured nothing. A rate on one arm cannot
detect discrimination. This revision measures the *difference between arms*.

The corpus: constructed, not discovered
---------------------------------------
Revision 1 mined pairs out of history and inferred, afterwards, which diff was
responsible for which sentence. Hand-adjudication found 8 of 18 were editorial
rewrites of true sentences and 9 of 18 carried evidence resolved to the wrong
file, leaving 5 usable pairs. Every later fix (module-path resolution, ``.rst``
filenames) narrowed that problem without solving corpus scale.

So the ground truth is built rather than found. ``corpus.py`` checks out a real
Flask commit's parent, authors a passage that is true there, and applies the
``src/`` half of that commit on top. The passage's truth value at HEAD is known
because it was chosen, and the falsifying diff is known because it was applied.
No resolver stands between the sentence and its evidence.

  falsified  12 passages made false by the commit applied over them. The
             correct action is to rewrite.

  accurate   12 passages the commit leaves true — the code they name really did
             change (a type annotation, a ``type: ignore``, a docstring), so
             Slate flags them exactly as it flags the falsified arm. The
             correct action is to decline.

All 24 are verified before the run: Slate raises exactly one task for the
passage, and the evidence names exactly the applied commit
(``corpus.py --verify``). Both arms are mechanically identical, so nothing but
the content of the diff can tell an agent which arm it is in.

What revision 3 changes, and what it deliberately does not
----------------------------------------------------------
Revision 2 ran all 24 trials. Discrimination passed decisively (11/12 falsified
rewritten, 0/12 accurate touched) and repair quality failed at 45%. Every one
of the six shortfalls was then read by hand, and all six were *correct repairs*
that the scorer misread, in two ways:

* four negated the old behaviour in order to retire it — "it no longer falls
  back to ``SERVER_NAME``", "(no longer a ``MethodViewType`` metaclass)".
  ``drops_old_fact`` asked whether the old fact was *mentioned*, which is not
  the same question as whether it is *asserted*. That is now negation-aware.
* two ``old_fact`` patterns named details the commit did not actually remove —
  ``open_resource`` really does still default to the platform encoding, and
  ``copy_current_request_context`` really is still applied at decoration time.
  Those were authoring errors in the corpus, and the patterns are removed.

The thresholds are **unchanged**. The point of writing them down first is lost
if a run that misses them is answered by lowering them, so revision 3 fixes the
instrument and keeps the bar exactly where revision 2 set it. Revision 2's
numbers are superseded, not re-scored: rescoring the recorded text with a
matcher built after reading that text would be choosing the metric to fit the
result. Revision 3's records come from fresh sessions.

Known bound on the new matcher: a rewrite that genuinely still asserts the old
behaviour while a negation cue happens to sit within 90 characters is scored as
having dropped it. That direction is a false pass, so it is the one to watch;
it is bounded by the primary also requiring the new fact to be stated, and by
adjudication remaining part of the report.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "corpus_rev2.json"

SOURCE_REPO = "https://github.com/pallets/flask.git"

MODEL = "claude-sonnet-5"
TRIALS_PER_ARM = 12

# Bumped whenever the corpus, prompt or metrics change in a way that makes
# older records incomparable — the same guard agentbench's TASK_REVISION gives.
#   1 — first pre-registration, after the freshness criterion was retired.
#   2 — constructed corpus; discrimination measured between arms; refs_resolve
#       demoted to descriptive; control matching fixed by construction.
#   3 — negation-aware fact matching, after revision 2's scorer marked six
#       correct repairs wrong. Thresholds deliberately unchanged; see below.
REVISION = 3

# Identical for both arms, and it must stay that way: the control arm only
# measures discrimination if the agent cannot tell which arm it is in. It says
# a passage "may be out of date", never that it is.
PROMPT_MUST_NOT_ASSERT_STALENESS = True


@dataclass
class TrialResult:
    """One agent session against one constructed passage."""
    item: str
    arm: str                  # falsified | accurate
    commit: str
    edited: bool              # did the passage change at all
    declined: bool            # answered NO CHANGE NEEDED
    kept_refs: bool           # the rewrite still names code in backticks
    states_new_fact: bool     # names the behaviour the diff introduced
    drops_old_fact: bool      # no longer asserts the behaviour the diff removed
    refs_resolved: int        # descriptive only — see the module docstring
    refs_total: int
    fresh_after: bool         # recorded, and circular — never a criterion
    before: str
    after: str

    @property
    def repaired(self) -> bool:
        """An edit that actually carries the new fact and drops the old one.

        Only meaningful on the falsified arm; on the accurate arm there is no
        new fact to state, and the fields are recorded as False.
        """
        return self.edited and self.states_new_fact and self.drops_old_fact


# --- the numbers, fixed in advance -----------------------------------------

# PRIMARY. Discrimination, as a difference between arms. An agent that edits
# everything and an agent that declines everything both score 0 here, which is
# the failure revision 1's single-arm threshold could not see. Both the size of
# the gap and its significance have to clear the bar — 12 per arm is small
# enough that a gap alone could be noise.
MIN_DISCRIMINATION = 0.40
MAX_DISCRIMINATION_P = 0.05

# PRIMARY. Of the falsified passages the agent chose to rewrite, the fraction
# whose rewrite states the behaviour the diff introduced and stops asserting
# the behaviour it removed. This is what "better, not merely different" means,
# and unlike freshness it is not something a repair can satisfy by existing:
# the facts were fixed when the corpus was built, before any agent saw them.
# Undefined when the agent edits nothing, and scored 0 in that case — an agent
# that never repairs has not demonstrated repair.
MIN_REPAIR_QUALITY = 0.70

# SECONDARY. A rewrite that names no code cannot be checked again by anything.
# `claims._emit` only emits a claim that has refs, so stripping the backticks
# is the cheapest way to make a doc green and never be caught being wrong
# again. Revision 1 passed this 18/18; it stays as a floor, not a hurdle.
MIN_KEPT_REFS = 0.95

# Recorded, never gates. See the module docstring for why this cannot be a
# criterion at any revision.
REFS_RESOLVE_IS_DESCRIPTIVE = True


def fisher_exact_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided p for the 2x2 table [[a, b], [c, d]], H1: a/(a+b) > c/(c+d).

    Rows are the arms, columns are edited / not edited. Stdlib only, like the
    rest of this project — the table is tiny and the exact sum is cheap.
    """
    n = a + b + c + d
    row1, col1 = a + b, a + c
    total = math.comb(n, col1)
    p = 0.0
    for k in range(a, min(row1, col1) + 1):
        p += math.comb(row1, k) * math.comb(n - row1, col1 - k) / total
    return p


def verdict(
    falsified_edited: int,
    falsified_total: int,
    accurate_edited: int,
    accurate_total: int,
    repair_quality: float,
    kept_refs_rate: float,
) -> tuple[bool, list[str]]:
    """Pass/fail against the pre-registered thresholds, with the reasons.

    Failing any one of these means Phases 2 and 3 of the plan do not get built
    and `slate repair` stays what it is today: a list for a human.
    """
    failures = []

    edit_falsified = falsified_edited / falsified_total if falsified_total else 0.0
    edit_accurate = accurate_edited / accurate_total if accurate_total else 0.0
    gap = edit_falsified - edit_accurate
    p = fisher_exact_greater(
        falsified_edited, falsified_total - falsified_edited,
        accurate_edited, accurate_total - accurate_edited,
    )

    if gap < MIN_DISCRIMINATION:
        failures.append(
            f"no discrimination: edited {edit_falsified:.0%} of falsified vs "
            f"{edit_accurate:.0%} of accurate passages, a gap of {gap:.0%}, "
            f"need {MIN_DISCRIMINATION:.0%}")
    if p > MAX_DISCRIMINATION_P:
        failures.append(
            f"gap not significant: Fisher exact p={p:.4f}, "
            f"need p<{MAX_DISCRIMINATION_P}")
    if repair_quality < MIN_REPAIR_QUALITY:
        failures.append(
            f"rewrites miss the fact: {repair_quality:.0%} state the new "
            f"behaviour and drop the old, need {MIN_REPAIR_QUALITY:.0%}")
    if kept_refs_rate < MIN_KEPT_REFS:
        failures.append(
            f"uncheckable prose: {kept_refs_rate:.0%} kept their refs, "
            f"need {MIN_KEPT_REFS:.0%}")

    return not failures, failures
