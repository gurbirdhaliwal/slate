"""Freshness engine — is each context doc still safe to trust?

Every doc carries a sync anchor (the commit it last reflected) and watch
globs (the code whose changes can invalidate it). Status is derived, never
stored:

    fresh               no watched path changed since the sync anchor
    stale               ≥1 watched path changed (committed or working tree)
    needs-verification  the anchor is missing or unresolvable (rebase,
                        squash, hand-deleted metadata) — staleness is
                        unknowable, which is worse than known-stale

This module is deliberately boring and exhaustively tested: a false "fresh"
is the one bug that destroys the product's promise (product doc §10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil, globs
from .context import DOC_SPECS, FRESH, NEEDS_VERIFICATION, STALE, ContextDoc, load_all

_CONTEXT_DOC_PATHS = {spec.rel_path for spec in DOC_SPECS}


@dataclass
class DocReport:
    doc: ContextDoc
    status: str
    changed_watched: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def rel_path(self) -> str:
        return self.doc.spec.rel_path


def evaluate_doc(root: Path, doc: ContextDoc) -> DocReport:
    anchor = doc.synced_commit
    if not anchor:
        return DocReport(doc, NEEDS_VERIFICATION, reason="no sync anchor recorded")
    if not gitutil.commit_exists(root, anchor):
        return DocReport(
            doc, NEEDS_VERIFICATION,
            reason=f"sync anchor {anchor} no longer resolvable (rebase/squash?)",
        )

    changed = gitutil.changed_files(root, anchor)
    # Context docs never invalidate context docs — humans editing (or Slate
    # syncing) the layer is the desired behavior; only *code* changes count.
    changed = [p for p in changed if p not in _CONTEXT_DOC_PATHS]
    hits = globs.filter_paths(doc.watches, changed) if doc.watches else []
    if hits:
        return DocReport(
            doc, STALE, changed_watched=hits,
            reason=f"{len(hits)} watched path(s) changed since {anchor}",
        )
    return DocReport(doc, FRESH, reason=f"synced at {anchor}")


def evaluate_all(root: Path) -> list[DocReport]:
    return [evaluate_doc(root, doc) for doc in load_all(root)]
