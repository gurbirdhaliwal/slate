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
merely different.

Why the original criterion was retired
--------------------------------------
The plan pre-registered "does Slate's own verifier turn the claim fresh, >=60%".
That criterion is dead and must not be revived. Authorship narrowing
(``freshness._prose_supersedes``) clears a claim whose prose is newer than the
code it names — and a repair is newer prose by definition, committed or not. So
freshness reads a timestamp the repair itself just updated. Measured directly:
replacing a stale sentence with "`engine.run` returns 9999 purple" turns the
doc **fresh**.

Freshness therefore cannot score a repair. It is circular by construction, and
the same circularity condemns the plan's Phase 2 gate as drafted ("re-run claim
evaluation, require the claim becomes fresh") — that gate would accept nonsense
from every trial.

What replaces it
----------------
Nothing here claims to measure truth; no deterministic check can. These measure
the two ways a repair can be actively *worse* than the staleness it replaces,
both of which are checkable without reading anything the agent wrote:

1. It can name code that does not exist — a confident hallucination, which is
   worse than a stale sentence because a stale sentence is at least about
   something real.
2. It can name no code at all. ``claims._emit`` only emits a claim that has
   refs, so a sentence stripped of its backticks is one that can never be
   caught being wrong again. That is the cheapest way to make a doc green and
   the most damaging.

Correctness is left to an adjudication pass over the results, by hand.

The arms
--------
Balanced, 18 each, and the control arm is the point. Phase 0.5 measured that
most claims Slate flags are prose that is still accurate — a file changed
somewhere near them. A repair loop that rewrites those is not fixing docs, it
is damaging them, and no amount of skill at the treatment arm compensates.

  repairs   sentences a maintainer later rewrote *because* the code moved.
            Mined from history: the doc edit that followed a code change is
            its own ground truth, and the maintainer's replacement is a gold
            answer to compare against. Median 48 commits stale before anyone
            noticed; the worst ran 558.

  controls  sentences Slate flags for the same reason — code they name changed
            — that the maintainer saw and deliberately left alone, and that
            survive unedited at HEAD. The correct action on these is to decline.

Both corpora are frozen beside this file so a re-run scores the same claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
REPAIRS = HERE / "corpus_repairs.json"
CONTROLS = HERE / "corpus_controls.json"

# Mined from these two repos: Slate itself, and Flask (already the agentbench
# subject, so its history is a known quantity here).
SOURCE_REPOS = ("slate", "https://github.com/pallets/flask.git")

MODEL = "claude-sonnet-5"
TRIALS_PER_ARM = 18

# Bumped whenever the corpus, prompt or metrics change in a way that makes
# older records incomparable — the same guard agentbench's TASK_REVISION gives.
#   1 — first pre-registration, after the freshness criterion was retired.
REVISION = 1

# Identical for both arms, and it must stay that way: the control arm only
# measures discrimination if the agent cannot tell which arm it is in. It says
# a sentence "may be out of date", never that it is.
PROMPT_MUST_NOT_ASSERT_STALENESS = True


@dataclass
class TrialResult:
    """One agent session against one claim."""
    arm: str                  # repairs | controls
    doc: str
    ref: str
    edited: bool              # did the sentence change at all
    declined: bool            # answered NO CHANGE NEEDED and left it alone
    kept_refs: bool           # the rewrite still names code
    refs_resolved: int        # named symbols that exist in the tree
    refs_total: int           # named symbols
    gold_overlap: float       # similarity to the maintainer's repair (repairs only)
    fresh_after: bool         # recorded, and circular — never a criterion


# --- the numbers, fixed in advance -----------------------------------------

# PRIMARY. Of rewrites naming at least one symbol, the fraction where every
# named symbol exists in the tree. Below this the loop introduces false claims
# faster than it removes them, and the write path should not be built.
MIN_REFS_RESOLVE = 0.90

# SECONDARY. A rewrite that names no code cannot be checked again by anything.
MIN_KEPT_REFS = 0.95

# SECONDARY, and the one most likely to fail: on claims that are flagged but
# still accurate, the agent must leave them alone. An agent that rewrites
# everything it is shown is not judging, it is complying.
MIN_CONTROL_DECLINE = 0.50

# Reported, never a gate: an approximate similarity against a human repair,
# where a low score can mean "wrong" or "differently worded".
GOLD_OVERLAP_IS_DESCRIPTIVE = True


def verdict(
    refs_resolve_rate: float, kept_refs_rate: float, control_decline_rate: float
) -> tuple[bool, list[str]]:
    """Pass/fail against the pre-registered thresholds, with the reasons.

    Failing any one of these means Phases 2 and 3 of the plan do not get built
    and `slate repair` stays what it is today: a list for a human.
    """
    failures = []
    if refs_resolve_rate < MIN_REFS_RESOLVE:
        failures.append(
            f"hallucination: {refs_resolve_rate:.0%} of rewrites fully resolve, "
            f"need {MIN_REFS_RESOLVE:.0%}")
    if kept_refs_rate < MIN_KEPT_REFS:
        failures.append(
            f"uncheckable prose: {kept_refs_rate:.0%} kept their refs, "
            f"need {MIN_KEPT_REFS:.0%}")
    if control_decline_rate < MIN_CONTROL_DECLINE:
        failures.append(
            f"no discrimination: declined on {control_decline_rate:.0%} of "
            f"accurate claims, need {MIN_CONTROL_DECLINE:.0%}")
    return not failures, failures
