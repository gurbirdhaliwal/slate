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
from .context import NEEDS_VERIFICATION, STALE, ContextDoc, load_all
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

    @property
    def rel_path(self) -> str:
        return self.report.rel_path


def verify_doc(root: Path, doc: ContextDoc) -> Verification:
    report = evaluate_doc(root, doc)

    refs = extract_path_refs(doc.body)
    missing = [r for r in refs if not (root / r).exists()]
    ref_score = 1.0 if not refs else (len(refs) - len(missing)) / len(refs)

    anchor = doc.synced_commit
    anchored = bool(anchor) and gitutil.commit_exists(root, anchor)
    if not anchored:
        if report.status == NEEDS_VERIFICATION:
            score = min(UNVERIFIABLE_CAP, ref_score * UNVERIFIABLE_CAP)
            return Verification(report, round(score, 2), len(refs), missing)
        if report.status == STALE:
            # Known-stale via the content digest: no quiet or drift credit.
            return Verification(report, round(W_REFERENCES * ref_score, 2), len(refs), missing)
        # Digest-recovered fresh: content is proven current, so the anchor's
        # age proxy is unnecessary — fall through with full quiet and drift.

    if report.content_verified:
        quiet = 1.0
    else:
        quiet = max(0.0, 1.0 - 0.1 * len(report.changed_watched))
    drift = max(0.0, 1.0 - 0.02 * gitutil.commits_since(root, anchor)) if anchored else 1.0
    score = W_REFERENCES * ref_score + W_WATCH_QUIET * quiet + W_ANCHOR * drift
    return Verification(report, round(score, 2), len(refs), missing)


def verify_all(root: Path) -> list[Verification]:
    return [verify_doc(root, doc) for doc in load_all(root)]
