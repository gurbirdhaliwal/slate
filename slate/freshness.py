"""Freshness engine — is each context doc still safe to trust?

Every doc carries a sync anchor (the commit it last reflected), watch globs
(the code whose changes can invalidate it), and a content digest of the
watched file set at sync time. Status is derived, never stored:

    fresh               no watched path changed since the sync anchor — or
                        watched paths changed but the doc provably still
                        checks out (a fresh scan generates the same facts,
                        and no hand-written claim references a changed path)
    stale               ≥1 watched path changed (committed or working tree)
                        in a way the doc can't be proven to survive
    needs-verification  the anchor is missing or unresolvable AND the
                        content digest can't vouch for the doc — staleness
                        is unknowable, which is worse than known-stale

An unresolvable anchor (rebase, squash-merge, hand-deleted metadata) first
falls back to the content digest: if the watched files' content is what it
was at the last sync, the doc is fresh and merely needs re-anchoring —
squash-merge workflows must not degrade the whole layer to a rumor.

This module is deliberately boring and exhaustively tested: a false "fresh"
is the one bug that destroys the product's promise (product doc §10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import context, generator, gitutil, globs, scanner
from .context import CONTEXT_DOC_PATHS, FRESH, NEEDS_VERIFICATION, STALE, ContextDoc, load_all
from .refs import extract_path_refs
from .scanner import RepoScan


@dataclass
class DocReport:
    doc: ContextDoc
    status: str
    changed_watched: list[str] = field(default_factory=list)
    reason: str = ""
    # True when the status was established by comparing content (scan facts
    # or the watched-file digest) rather than by an all-quiet anchor diff.
    content_verified: bool = False

    @property
    def rel_path(self) -> str:
        return self.doc.spec.rel_path


def evaluate_doc(root: Path, doc: ContextDoc, scan: RepoScan | None = None) -> DocReport:
    get_scan = (lambda: scan) if scan is not None else _scan_once(root)
    return _evaluate(root, doc, get_scan)


def evaluate_all(root: Path) -> list[DocReport]:
    get_scan = _scan_once(root)  # at most one scan for the whole layer
    return [_evaluate(root, doc, get_scan) for doc in load_all(root)]


def _scan_once(root: Path) -> Callable[[], RepoScan]:
    cache: list[RepoScan] = []

    def get() -> RepoScan:
        if not cache:
            cache.append(scanner.scan(root))
        return cache[0]

    return get


def _evaluate(root: Path, doc: ContextDoc, get_scan: Callable[[], RepoScan]) -> DocReport:
    anchor = doc.synced_commit
    if not anchor:
        return DocReport(doc, NEEDS_VERIFICATION, reason="no sync anchor recorded")
    if not gitutil.commit_exists(root, anchor):
        return _evaluate_orphaned(root, doc, anchor)

    changed = gitutil.changed_files(root, anchor)
    # Context docs never invalidate context docs — humans editing (or Slate
    # syncing) the layer is the desired behavior; only *code* changes count.
    changed = [p for p in changed if p not in CONTEXT_DOC_PATHS]
    hits = globs.filter_paths(doc.watches, changed) if doc.watches else []
    if not hits:
        return DocReport(doc, FRESH, reason=f"synced at {anchor}")
    if _claims_still_check_out(doc, hits, get_scan):
        return DocReport(
            doc, FRESH, changed_watched=hits, content_verified=True,
            reason=(
                f"{len(hits)} watched path(s) changed since {anchor}, but the doc "
                "still checks out (a fresh scan generates the same facts)"
            ),
        )
    return DocReport(
        doc, STALE, changed_watched=hits,
        reason=f"{len(hits)} watched path(s) changed since {anchor}",
    )


def _claims_still_check_out(
    doc: ContextDoc, hits: list[str], get_scan: Callable[[], RepoScan]
) -> bool:
    """True when the watched changes provably did not invalidate the doc.

    Watch globs are deliberately broad, so most edits inside a watched tree
    don't actually change what the doc claims (editing a function body never
    moves a module). Requiring proof keeps "stale" meaning "sync would change
    something" instead of "some watched file was touched". Two conditions:

    - regenerating the auto-block from a fresh scan yields exactly what is on
      disk (an LLM prose paragraph synced above the facts is tolerated — the
      facts are the claims);
    - no hand-written section references a changed path, so the change cannot
      have invalidated a human claim the scan can't see.

    Anything unprovable stays stale — a false "fresh" is the catastrophic bug.
    """
    if not doc.spec.generated:
        return False
    current = context.get_auto_block(doc.body)
    if current is None:
        return False
    regenerated = generator.auto_content(doc.spec, get_scan())
    if current != regenerated and not current.endswith("\n\n" + regenerated):
        return False
    begin = doc.body.find(context.AUTO_BEGIN)
    end = doc.body.find(context.AUTO_END) + len(context.AUTO_END)
    human_text = doc.body[:begin] + doc.body[end:]
    for ref in extract_path_refs(human_text):
        for hit in hits:
            if hit == ref or hit.startswith(ref + "/"):
                return False
    return True


def _evaluate_orphaned(root: Path, doc: ContextDoc, anchor: str) -> DocReport:
    """Anchor unresolvable (rebase/squash) — let the content digest decide.

    needs-verification is reserved for the truly unknowable case: no digest
    recorded (pre-digest layer, or hand-stripped metadata).
    """
    recorded = doc.meta.get("slate_synced_digest")
    if not recorded:
        return DocReport(
            doc, NEEDS_VERIFICATION,
            reason=f"sync anchor {anchor} no longer resolvable (rebase/squash?)",
        )
    if context.watched_digest(root, doc.watches) == str(recorded):
        return DocReport(
            doc, FRESH, content_verified=True,
            reason=(
                f"sync anchor {anchor} was rewritten (rebase/squash), but the watched "
                "content matches the last sync — run `slate sync` to re-anchor"
            ),
        )
    # Without the anchor there is no commit range to enumerate; the working
    # tree still yields whatever evidence it can.
    changed = [p for p in gitutil.changed_files(root, None) if p not in CONTEXT_DOC_PATHS]
    hits = globs.filter_paths(doc.watches, changed) if doc.watches else []
    return DocReport(
        doc, STALE, changed_watched=hits,
        reason=(
            f"sync anchor {anchor} was rewritten and watched content changed "
            "since the last sync"
        ),
    )
