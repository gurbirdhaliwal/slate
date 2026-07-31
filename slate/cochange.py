"""Co-change coupling — the facts a repo scan cannot see and grep cannot reach.

Every other fact Slate generates describes the tree *as it stands*: file
counts, module boundaries, import edges. An agent can rederive all of it in
two or three tool calls, which is exactly what the benchmark found — a fresh
Slate layer changed nothing an agent did, because it contained nothing the
agent could not cheaply look up (`benchmarks/agentbench/RESULTS.md`).

History is different. Which files habitually change *together* is not in the
tree at any commit; it is only in the log. Measured across 15 benchmark
sessions, **no agent ran `git log`, `git blame` or `git show` even once**.
That is a structural blind spot, not a preference — the agent's tools are
excellent at "where is X?" and have nothing to say about "what else moves
when X moves?", which is the question that decides whether a change is
complete.

On the benchmark's own task the signal is predictive, but only once the
selection is right. The fix spans `app.py`, `ctx.py` and `helpers.py`; with
the tuning below, two of those three pairs land in Flask's top twelve and
`app.py`<->`helpers.py` ranks first. Ranked by raw co-occurrence instead,
none of them appear at all — the table fills with `CHANGES.rst`. The
difference between this being a useful fact and decorative noise is entirely
in `strength()` and the code-file restriction, not in the idea.

Three deliberate limits, each protecting a property the freshness engine
depends on:

**Bulk commits are excluded.** A reformat touching 300 files would couple
every pair of them and drown the real signal; commits above
``MAX_FILES_PER_COMMIT`` are skipped entirely. This is the single biggest
determinant of whether the output is useful or noise.

**Counts are computed but never rendered.** Rendering "43×" would change the
auto-block on virtually every commit that touches two watched files, so
`architecture.md` would sit stale permanently and readers would learn to
ignore the staleness signal — destroying the thing the product sells. Pairs
are *selected* by strength and *rendered* alphabetically, so the block only
changes when the membership of the top set changes, which is rare.

**Only files still in the tree.** A pair naming a deleted file is a claim
about a repo that no longer exists.

Output is fully sorted and therefore byte-identical across runs and across
``PYTHONHASHSEED`` — a fact that rendered differently run to run would
manufacture false `stale`, the failure §10 forbids.
"""

from __future__ import annotations

import itertools
import os
from collections import Counter
from pathlib import Path
from typing import Callable

from . import gitutil

# OFF BY DEFAULT, on the evidence. Set SLATE_COCHANGE=1 to re-enable.
#
# The idea survived every check except the one that counts. The facts are
# correct, deterministic, cheap to compute, and name exactly the file the
# benchmark's agents miss. Both deliveries were then measured against `bare`
# on the same task, 6 trials each:
#
#   as a rendered doc section   the layer named app.py <-> sessions.py and
#                               every trial missed sessions.py anyway; the
#                               two trials that opened architecture.md
#                               scored *worse* on scope than those that
#                               did not.
#   injected at the edit        hook fired 6/6, named sessions.py in 3/6,
#                               and 0 of those 3 edited it. Context cost
#                               rose 46% over bare (p=0.0411) — the only
#                               significant result in the sweep, against us.
#
# Keeping it on would mean charging every session for a fact that was
# measured twice and moved nothing. The code and its tests stay because the
# experiment is worth repeating on a different task shape — a repo where
# coupling is less discoverable, or an agent with weaker search — but it
# does not ship on by default until something moves.
ENABLED_ENV = "SLATE_COCHANGE"


def enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "").strip().lower() in {"1", "true", "yes"}

# How far back to look. Deep enough to see real coupling in a mature repo,
# shallow enough that the scan stays sub-second on a large history.
COMMITS = 400

# A commit touching more than this is a refactor, release bump or reformat.
# Including one would assert coupling between every pair of files it happened
# to sweep up.
MAX_FILES_PER_COMMIT = 25

# A pair has to recur before it is a fact rather than a coincidence.
MIN_COUNT = 3

# Keep the rendered block small; this lands in every session's context.
TOP_K = 12


def _tracked(files: list[str]) -> set[str]:
    """The files coupling is computed over.

    The context layer is excluded, and it is not an optional refinement.
    `slate sync` rewrites and commits every generated doc in one commit, so
    the layer is the most tightly coupled group of files in any repo that
    uses Slate — left in, it wins every slot and the output reduces to "your
    Slate docs change with your Slate docs".

    Code files only, and that is what makes the output useful rather than
    merely true. Measured on Flask: with docs and config included, the top of
    the table is `CHANGES.rst` paired with everything and CI workflows paired
    with each other — real coupling, but release hygiene rather than "what
    else does this change touch?", and 13 of 15 benchmark sessions found
    CHANGES.rst unaided anyway.
    """
    # Lazy imports break the cochange<->context<->scanner cycle, the same way
    # `scanner` defers `imports`.
    from .context import CONTEXT_DOC_PATHS
    from .scanner import CODE_EXTENSIONS

    return {
        f for f in files
        if f not in CONTEXT_DOC_PATHS and Path(f).suffix.lower() in CODE_EXTENSIONS
    }


def _strength(
    counts: Counter[tuple[str, str]], solo: Counter[str]
) -> Callable[[tuple[str, str]], float]:
    """Co-occurrence weighted by how *specific* that co-occurrence is.

    Both obvious measures fail, in opposite directions, and both failures were
    observed on real repos rather than reasoned about:

    - **Raw count** ranks *hub* files first. A changelog or lockfile touched
      by nearly every commit racks up a high count with every partner. On
      Flask this filled six of twelve slots with `CHANGES.rst` pairs and
      pushed out `app.py`<->`ctx.py`.
    - **Jaccard alone** ranks *rare* files first. Two docs edited three times,
      always together, score a perfect 1.0 and outrank a pair that co-changed
      twelve times. On Flask this evicted the ground-truth pair entirely in
      favour of `docs/*.rst`.

    `count x jaccard` (equivalently count^2/union) needs a pair to be both
    frequent and specific, which is exactly the pair worth telling someone
    about. A hub scores low because its union is huge; a rarity scores low
    because its count is small.
    """
    def score(pair: tuple[str, str]) -> float:
        a, b = pair
        union = solo[a] + solo[b] - counts[pair]
        return counts[pair] ** 2 / union if union else 0.0

    return score


def partners(
    root: Path,
    files: list[str],
    path: str,
    *,
    commits: int = COMMITS,
    max_files_per_commit: int = MAX_FILES_PER_COMMIT,
    min_count: int = MIN_COUNT,
    limit: int = 3,
) -> list[tuple[str, int]]:
    """Files that historically change alongside ``path``, strongest first.

    The per-file view `compute` cannot give: the rendered table is a repo-wide
    top-twelve, so a file whose coupling is real but ranks thirteenth appears
    nowhere. Asked about one file directly, the same evidence answers "what
    else moves when *this* moves" without competing against every other pair
    in the repo.

    Returns ``(partner_path, co_change_count)``. Counts are safe to surface
    here — unlike the rendered auto-block, hook output is not a tracked doc,
    so a number that moves every commit cannot manufacture a false `stale`.

    Never raises; an unreadable history yields no partners.
    """
    tracked = _tracked(files)
    if path not in tracked:
        return []
    counts, solo = _pair_counts(root, tracked, commits, max_files_per_commit)
    if not counts:
        return []
    score = _strength(counts, solo)
    mine = [
        (pair, counts[pair]) for pair in counts
        if path in pair and counts[pair] >= min_count
    ]
    mine.sort(key=lambda item: (-score(item[0]), item[0]))
    out = []
    for pair, count in mine[:limit]:
        other = pair[1] if pair[0] == path else pair[0]
        out.append((other, count))
    return out


def compute(
    root: Path,
    files: list[str],
    *,
    commits: int = COMMITS,
    max_files_per_commit: int = MAX_FILES_PER_COMMIT,
    min_count: int = MIN_COUNT,
    top_k: int = TOP_K,
) -> list[tuple[str, str]]:
    """Files that repeatedly change in the same commit.

    Returns at most ``top_k`` pairs, each ``(a, b)`` with ``a < b``, sorted
    alphabetically. Selection is by strength; the ordering is alphabetical so
    that a shift in counts does not rewrite the rendered block.

    Never raises: a repo with no history, a shallow clone, or a git failure
    yields no facts rather than breaking the scan.
    """
    counts, solo = _pair_counts(
        root, _tracked(files), commits, max_files_per_commit)
    if not counts:
        return []
    score = _strength(counts, solo)
    ranked = sorted(
        (p for p, n in counts.items() if n >= min_count),
        # Strength first; the pair's names break ties so selection stays
        # deterministic when several score identically.
        key=lambda p: (-score(p), p),
    )
    return sorted(ranked[:top_k])


def _pair_counts(
    root: Path, tracked: set[str], commits: int, max_files_per_commit: int
) -> tuple[Counter[tuple[str, str]], Counter[str]]:
    """Co-occurrence counts, plus how often each file changed at all.

    The second half is what makes hub files rankable: without it there is no
    way to tell "these two belong together" from "this one changes with
    everything".
    """
    try:
        log = gitutil._git(
            root, "log", f"-n{commits}", "--format=%H", "--name-only",
            "--no-merges", "--no-renames",
        )
    except (gitutil.GitError, FileNotFoundError, OSError):
        return Counter(), Counter()

    counts: Counter[tuple[str, str]] = Counter()
    solo: Counter[str] = Counter()
    for changed in _commits(log):
        # Restrict to files that still exist before applying the bulk cutoff,
        # so a commit that touched 40 files of which 4 survive still counts.
        present = sorted({f for f in changed if f in tracked})
        if len(present) < 2 or len(present) > max_files_per_commit:
            continue
        for path in present:
            solo[path] += 1
        for pair in itertools.combinations(present, 2):
            counts[pair] += 1
    return counts, solo


def _commits(log: str) -> list[list[str]]:
    """Split `git log --format=%H --name-only` into per-commit path lists."""
    out: list[list[str]] = []
    current: list[str] | None = None
    for line in log.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if _is_sha(line):
            if current is not None:
                out.append(current)
            current = []
        elif current is not None:
            current.append(gitutil._unquote(line))
    if current is not None:
        out.append(current)
    return out


def _is_sha(line: str) -> bool:
    return len(line) == 40 and all(c in "0123456789abcdef" for c in line)
