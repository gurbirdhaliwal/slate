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
                              sync anchor, decaying 0.1 per changed path
    anchor drift (0.15)       decays with commits landed since the anchor,
                              even when no watched path changed — old
                              attestations are weaker than recent ones

A doc with no sync anchor is capped at 0.25: unverifiable ≠ trustworthy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import gitutil
from .context import ContextDoc, load_all
from .freshness import DocReport, evaluate_doc

W_REFERENCES = 0.5
W_WATCH_QUIET = 0.35
W_ANCHOR = 0.15
UNVERIFIABLE_CAP = 0.25

# Path-like tokens: markdown link targets and backticked segments with a "/",
# or well-known root files. Anchors/URLs are excluded.
_LINK = re.compile(r"\]\(([^)#\s]+)\)")
_TICKED = re.compile(r"`([A-Za-z0-9_./-]+)`")
_ROOT_FILES = {"Makefile", "README.md", "pyproject.toml", "package.json", "pom.xml"}


@dataclass
class Verification:
    report: DocReport
    score: float
    referenced: int
    missing: list[str]

    @property
    def rel_path(self) -> str:
        return self.report.rel_path


def extract_path_refs(body: str) -> list[str]:
    refs: set[str] = set()
    for match in _LINK.finditer(body):
        target = match.group(1)
        if "://" not in target:
            refs.add(target.strip("/"))
    for match in _TICKED.finditer(body):
        token = match.group(1)
        if "/" in token.rstrip("/") or token in _ROOT_FILES:
            refs.add(token.strip("/"))
    return sorted(r for r in refs if r and not r.startswith("."))


def verify_doc(root: Path, doc: ContextDoc) -> Verification:
    report = evaluate_doc(root, doc)

    refs = extract_path_refs(doc.body)
    missing = [r for r in refs if not (root / r).exists()]
    ref_score = 1.0 if not refs else (len(refs) - len(missing)) / len(refs)

    anchor = doc.synced_commit
    if not anchor or not gitutil.commit_exists(root, anchor):
        score = min(UNVERIFIABLE_CAP, ref_score * UNVERIFIABLE_CAP)
        return Verification(report, round(score, 2), len(refs), missing)

    quiet = max(0.0, 1.0 - 0.1 * len(report.changed_watched))
    drift = max(0.0, 1.0 - 0.02 * gitutil.commits_since(root, anchor))
    score = W_REFERENCES * ref_score + W_WATCH_QUIET * quiet + W_ANCHOR * drift
    return Verification(report, round(score, 2), len(refs), missing)


def verify_all(root: Path) -> list[Verification]:
    return [verify_doc(root, doc) for doc in load_all(root)]
