"""Verification score — a 0.00–1.00 trust signal per context doc.

Freshness (freshness.py) answers "did watched code change?". The
verification score answers the softer question an AI has to make a call on:
*how much of this doc still checks out against the repo right now?*

The MVP score is deliberately simple and fully deterministic (product doc
§8) — three weighted components:

    reference validity (0.5)  fraction of repo paths the doc mentions that
                              still exist; a doc pointing at deleted files
                              is actively misleading
    watch quiet (0.35)        1.0 when no watched path changed since the
                              sync anchor — or when the doc is content-
                              verified despite changes — decaying 0.1 per
                              unverified changed path
    anchor drift (0.15)       decays with commits landed since the anchor,
                              even when no watched path changed — old
                              attestations are weaker than recent ones

An orphaned anchor is scored by what the content digest can prove: digest
matches → full scoring (the doc is provably current); digest mismatch →
known-stale, only references count; no digest → capped at 0.25, because
unverifiable ≠ trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import gitutil
from .context import FRESH, NEEDS_VERIFICATION, STALE, ContextDoc, load_all
from .freshness import DocReport, evaluate_doc
from .refs import extract_path_refs  # re-exported for compatibility  # noqa: F401

W_REFERENCES = 0.5
W_WATCH_QUIET = 0.35
W_ANCHOR = 0.15
UNVERIFIABLE_CAP = 0.25


@dataclass
class Verification:
    report: DocReport
    score: float
    referenced: int
    missing: list[str]
    total_claims: int = 0
    suspect_claims: int = 0

    @property
    def rel_path(self) -> str:
        return self.report.rel_path


def verify_doc(root: Path, doc: ContextDoc) -> Verification:
    report = evaluate_doc(root, doc)

    refs = extract_path_refs(doc.body)
    missing = [r for r in refs if not (root / r).exists()]
    ref_score = 1.0 if not refs else (len(refs) - len(missing)) / len(refs)

    total = len(report.claims)
    suspect = len(report.suspect_claims)

    anchor = doc.synced_commit
    anchored = bool(anchor) and gitutil.commit_exists(root, anchor)
    if not anchored:
        if report.status == NEEDS_VERIFICATION:
            score = min(UNVERIFIABLE_CAP, ref_score * UNVERIFIABLE_CAP)
            return Verification(report, round(score, 2), len(refs), missing, total, suspect)
        if report.status == STALE:
            # Known-stale via the content digest: no quiet or drift credit.
            score = W_REFERENCES * ref_score
            return Verification(report, round(score, 2), len(refs), missing, total, suspect)
        # Digest-recovered fresh: content is proven current, so the anchor's
        # age proxy is unnecessary — fall through with full quiet and drift.

    quiet = _claim_quiet(report)
    drift = max(0.0, 1.0 - 0.02 * gitutil.commits_since(root, anchor)) if anchored else 1.0
    score = W_REFERENCES * ref_score + W_WATCH_QUIET * quiet + W_ANCHOR * drift
    return Verification(report, round(score, 2), len(refs), missing, total, suspect)


def _claim_quiet(report: DocReport) -> float:
    """Watch-quiet, resolved to the *claim* (product doc §8, Part B).

    Instead of a flat penalty per changed path — which drags a solid doc amber
    for one suspect sentence — quiet is the fraction of the doc's claims that
    still check out. One suspect claim in six costs far less than six in six.
    A content-verified doc has every claim fresh, so it keeps full quiet, same
    as before this refinement.
    """
    if report.claims:
        fresh = sum(1 for c in report.claims if c.status == FRESH)
        return fresh / len(report.claims)
    # No claims derived (no watched change, or an orphaned path): quiet unless
    # bare changed-path evidence says otherwise.
    if report.content_verified or not report.changed_watched:
        return 1.0
    return max(0.0, 1.0 - 0.1 * len(report.changed_watched))


def verify_all(root: Path) -> list[Verification]:
    return [verify_doc(root, doc) for doc in load_all(root)]
