"""Repair tasks — a suspect claim, scoped enough for someone to act on.

This module reads verdicts and turns them into a worklist. It computes no
trust of its own, calls no model, and writes nothing; `freshness` decides what
is suspect and `cli` decides what to print, exactly as `mcp` and `claudehook`
already do. A second opinion about whether a doc is fresh would be a second
thing that can disagree.

**Generated facts are not repair tasks.** `slate sync` rewrites the auto-block
deterministically, in milliseconds, for zero tokens — measured over this
repo's whole history, generated drift is the *only* staleness that ever
occurred, and handing it to a model would be strictly worse than the machinery
that already fixes it. Only hand-written claims land here, because they are
the only ones a rewrite is the answer to.

**A task is not proof the prose is wrong.** `scope` carries which resolution
reached the verdict:

- ``symbol`` — the referenced symbol provably moved. Strong evidence.
- ``path``   — a referenced file changed *somewhere*. The claim may be
  untouched, and on this repo's corpus most path-scoped flags were prose that
  was still accurate.

Anything consuming these tasks has to let "this claim is still correct" be an
answer, or its default action on the common case is rewriting correct prose.

**Verification (`verify_repair`) decides admissibility, never freshness.** The
agent proposes and a deterministic check disposes, the asymmetry a proof checker
uses — but the check is about the *edit*, not about whether the doc is now
accurate. Nothing here can re-anchor a doc; that stays where it has always been,
with `freshness.evaluate` and `slate mark`. Two candidate gates were measured
dead in Phase 0 and must not come back:

- **not freshness** — a repair is newer prose by definition, so authorship
  narrowing clears it whatever it says. Replacing a stale sentence with
  "`engine.run` returns 9999 purple" turns the doc fresh.
- **not "every named symbol resolves"** — it cannot express deletion, and prose
  about removed API is correct prose. repairbench rev 3 measured 4 of 14 symbols
  in *correct* rewrites failing to resolve.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil
from .claims import human_claims
from .freshness import CLAIM_FRESH, DocReport, symbol_files


@dataclass
class RepairTask:
    doc_path: str
    line: int                  # 1-based line in the file
    end_line: int
    section: str               # enclosing heading, for orientation
    text: str
    status: str                # stale | unknowable
    scope: str                 # symbol | path — how strong the evidence is
    risk: list[str] = field(default_factory=list)   # refs that put it at risk
    anchor: str = ""           # the doc's sync anchor: the diff starts here
    commits: dict[str, str] = field(default_factory=dict)  # ref -> newest commit
    # Refs whose change is not committed yet. Distinguished from "no evidence"
    # because the answer to "show me the diff" is `git diff`, not `git show`.
    uncommitted: list[str] = field(default_factory=list)

    @property
    def evidence_is_strong(self) -> bool:
        return self.scope == "symbol"

    def as_dict(self) -> dict:
        return {
            "doc_path": self.doc_path,
            "line": self.line,
            "end_line": self.end_line,
            "section": self.section,
            "text": self.text,
            "status": self.status,
            "scope": self.scope,
            "risk": self.risk,
            "anchor": self.anchor,
            "commits": self.commits,
            "uncommitted": self.uncommitted,
        }


def repair_tasks(
    root: Path, reports: list[DocReport], *, with_commits: bool = True
) -> list[RepairTask]:
    """Every hand-written claim a doc no longer vouches for.

    Ordered strongest evidence first, then by document position, so the head
    of the list is where a reader — or an agent — should start.
    """
    tasks: list[RepairTask] = []
    for report in reports:
        anchor = report.doc.synced_commit or ""
        for claim in report.claims:
            if claim.kind != "human" or claim.status == CLAIM_FRESH:
                continue
            commits, uncommitted = (
                _commits_for(root, claim.risk, report.changed_watched, anchor)
                if with_commits and anchor else ({}, [])
            )
            tasks.append(RepairTask(
                doc_path=claim.doc_path or report.rel_path,
                line=claim.line, end_line=claim.end_line,
                section=claim.section, text=claim.text,
                status=claim.status, scope=claim.scope,
                risk=list(claim.risk), anchor=anchor, commits=commits,
                uncommitted=uncommitted,
            ))
    tasks.sort(key=lambda t: (not t.evidence_is_strong, t.doc_path, t.line))
    return tasks


# --------------------------------------------------------------------------
# verification: is this proposed edit admissible?

REPAIRED = "repaired"      # the target claim was rewritten, and only it
UNCHANGED = "unchanged"    # the claim was left alone — a real, correct answer
REJECTED = "rejected"


@dataclass
class Verdict:
    outcome: str            # repaired | unchanged | rejected
    reasons: list[str] = field(default_factory=list)
    claims_before: int = 0
    claims_after: int = 0

    @property
    def ok(self) -> bool:
        return self.outcome != REJECTED

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "ok": self.ok,
            "reasons": self.reasons,
            "claims_before": self.claims_before,
            "claims_after": self.claims_after,
        }


def verify_repair(before: str, after: str, target: str) -> Verdict:
    """Is this rewrite of `target` an admissible edit to the doc body?

    Pure, and deliberately so: no tree, no git, no scan, no model. Everything
    it consults is the two bodies and the segmenter, so there is no path by
    which it can consult — or accidentally reimplement — the freshness engine.
    The drafted signature took `root` and `doc`; neither is reachable by any
    check that survived Phase 0, and an unused handle to the repo is an
    invitation to grow one.

    Three things have to hold, and they are all about damage rather than truth:

    1. **The claim still exists, carrying refs.** `claims._emit` only emits a
       unit that references code, so a sentence stripped of its backticks stops
       being a claim at all — it vanishes from `human_claims`, the doc goes
       green, and nothing can ever catch it being wrong again. That is a false
       `fresh` manufactured by the repair loop itself, the one failure the
       product forbids outright, introduced by the feature meant to serve it.
    2. **Nothing else moved.** A repair that fixes claim 3 and quietly edits
       claim 5 has spent the doc's credibility on an edit nobody reviewed.
    3. **"No change needed" is a pass.** It was the correct action in 12 of
       repairbench rev 3's 24 trials, and on real history most flagged claims
       are prose that is still accurate. A gate that only recognises a
       successful rewrite scores the right answer as a failure.

    Truth is not checked, because no deterministic check reaches it. A verdict
    of `repaired` says the edit is well-formed and confined, never that it is
    correct.
    """
    before_claims = human_claims(before)
    after_claims = human_claims(after)
    verdict = Verdict(REJECTED, [], len(before_claims), len(after_claims))

    matched = [c for c in before_claims if c.text == target]
    if not matched:
        verdict.reasons.append(
            "the target claim is not in the document as given, so there is "
            "nothing to verify against")
        return verdict
    section = matched[0].section

    removed = Counter(c.text for c in before_claims) - Counter(
        c.text for c in after_claims)
    added = Counter(c.text for c in after_claims) - Counter(
        c.text for c in before_claims)

    # Re-wrapping a paragraph changes the bytes and not the claim: the
    # segmenter joins a unit's lines before emitting it. Treating that as an
    # edit would reject the most common harmless thing an editor does.
    if not removed and not added:
        verdict.outcome = UNCHANGED
        return verdict

    others = sorted(set(removed) - {target})
    if others:
        verdict.reasons.append(
            f"{len(others)} other claim(s) changed or disappeared: "
            + "; ".join(_abbreviate(text) for text in others))
    if target not in removed:
        verdict.reasons.append(
            "the target claim was left alone while other prose changed")
    if not added:
        verdict.reasons.append(
            "the rewrite names no code, so the claim is gone from the doc's "
            "trust surface and can never be checked again")
    for text in sorted(added):
        claim = next(c for c in after_claims if c.text == text)
        if claim.section != section:
            verdict.reasons.append(
                f"new claim landed under '{claim.section}', not '{section}': "
                + _abbreviate(text))

    if not verdict.reasons:
        verdict.outcome = REPAIRED
    return verdict


def _abbreviate(text: str, width: int = 60) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


# --------------------------------------------------------------------------
# the other door: attestation
#
# `verify_repair` stops a *repair* deleting a claim's refs. It governs one
# path. `slate mark` re-anchors a human-owned doc directly, and measured over
# 20 benchmark sessions that is the door agents actually walked through: edit
# `read-next.md` with an ordinary file tool, then run `slate mark`, and the doc
# is green with nothing having checked the prose.
#
# The guard is the same invariant, asked at attestation time: a claim that was
# in the doc at its last anchor should still be there. Losing one is not
# forbidden — prose gets deleted for good reasons — but it is not something to
# do by accident while attesting that the doc is accurate.


@dataclass
class ClaimLoss:
    before: int              # claims in the doc at its anchor
    after: int               # claims in it now
    vanished: list[str] = field(default_factory=list)

    @property
    def dropped(self) -> int:
        """How many claims the doc no longer has. The thing to refuse on.

        Counted, not matched by text, because a *repair* changes a claim's
        wording — that is what repairing is. Refusing on "this exact sentence
        is gone" would block every honest repair from being attested, which
        would make the guard a reason to stop using the feature it protects.
        `verify_repair` draws the same line for the same reason.
        """
        return max(0, self.before - self.after)


def claim_loss(root: Path, doc, anchor: str | None = None) -> ClaimLoss:
    """Compare a doc's claims against the version at its anchor.

    A zero-loss result when there is nothing to compare against — no anchor,
    no commit, a doc that did not exist there. An unanswerable question is not
    evidence of loss, and `mark` must stay usable in a fresh repo.
    """
    from . import frontmatter

    anchor = anchor or doc.synced_commit
    if not anchor:
        return ClaimLoss(0, 0)
    previous = gitutil.file_at_commit(root, doc.spec.rel_path, anchor)
    if previous is None:
        return ClaimLoss(0, 0)
    _, before_body = frontmatter.parse(previous)
    before = [c.text for c in human_claims(before_body)]
    now = {c.text for c in human_claims(doc.body)}
    # Named for the error message only. A rewritten claim shows up here and is
    # *not* counted as a loss — the count above is what decides.
    return ClaimLoss(len(before), len(now),
                     sorted(t for t in set(before) - now))


def replace_claim(body: str, target: str, replacement: str) -> str:
    """Swap one claim's lines for new text, by span rather than by string.

    The segmenter joins a unit's lines before reporting it, so the claim text a
    caller quotes back rarely appears in the file verbatim — a plain string
    replace would silently miss every wrapped paragraph, which is the bug that
    dropped 10 of repairbench rev 1's 18 controls.

    A target that is not present returns the body untouched, so the caller's
    `verify_repair` sees an unchanged document and rejects it. Failing into "no
    edit" is the safe direction; guessing which claim was meant is not.
    """
    for claim in human_claims(body):
        if claim.text != target:
            continue
        lines = body.splitlines()
        lines[claim.line - 1:claim.end_line] = replacement.splitlines()
        return "\n".join(lines) + ("\n" if body.endswith("\n") else "")
    return body


def _commits_for(
    root: Path, risk: list[str], hits: list[str], anchor: str
) -> tuple[dict[str, str], list[str]]:
    """Newest commit since `anchor` behind each risk ref, and the rest.

    A ref naming a path is asked about directly; a ``module.symbol`` ref is
    resolved to the changed files that could host it, the same way the
    freshness engine resolves it. This is a lookup, not a second opinion — the
    verdict was already reached before any of this runs.

    A ref with no commit is not evidence-free: the file *is* among the hits,
    so the change exists and simply is not committed yet. Saying which is
    which is the difference between `git show` and `git diff`.
    """
    commits: dict[str, str] = {}
    uncommitted: list[str] = []
    for ref in risk:
        direct = [h for h in hits if h == ref or h.startswith(ref + "/")]
        candidates = direct or symbol_files(ref, hits)
        for path in candidates:
            sha = gitutil.last_change_commit(root, path, anchor)
            if sha:
                commits[ref] = sha
                break
        else:
            if candidates:
                uncommitted.append(ref)
    return commits, uncommitted
