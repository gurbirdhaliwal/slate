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

from . import context, generator, gitutil, globs, scanner, symbols
from .context import CONTEXT_DOC_PATHS, FRESH, NEEDS_VERIFICATION, STALE, ContextDoc, load_all
from .refs import extract_path_refs, extract_symbol_refs
from .scanner import CODE_EXTENSIONS, RepoScan


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
    if _claims_still_check_out(root, doc, anchor, hits, get_scan):
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
    root: Path, doc: ContextDoc, anchor: str | None,
    hits: list[str], get_scan: Callable[[], RepoScan],
) -> bool:
    """True when the watched changes provably did not invalidate the doc.

    Watch globs are deliberately broad, so most edits inside a watched tree
    don't actually change what the doc claims (editing a function body never
    moves a module). Requiring proof keeps "stale" meaning "sync would change
    something" instead of "some watched file was touched". Three conditions:

    - regenerating the auto-block from a fresh scan yields exactly what is on
      disk (an LLM prose paragraph synced above the facts is tolerated — the
      facts are the claims);
    - no hand-written section references a changed *path* — a claim about a
      whole file can't be proven to survive an edit anywhere in it;
    - every hand-written ``module.symbol`` reference resolves to a symbol whose
      lines were *not* among the change, so a claim about ``context.get_auto_block``
      only stales when that function actually moved (§ symbol resolution).

    Anything unprovable — an unparseable file, an unresolvable symbol — stays
    stale. A false "fresh" is the catastrophic bug (product doc §10); symbol
    resolution may only ever *narrow* stale→fresh, never the reverse.
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

    # A claim about a whole file (a path reference) can't be narrowed — any
    # edit inside it might touch what the claim depends on. Unchanged behavior.
    for ref in extract_path_refs(human_text):
        for hit in hits:
            if hit == ref or hit.startswith(ref + "/"):
                return False

    symbol_refs = extract_symbol_refs(human_text)
    if not symbol_refs:
        return True
    changed = _changed_symbols(root, anchor, hits)
    all_stems = {
        _stem(f) for f in get_scan().files if _is_code(f)
    }
    for ref in symbol_refs:
        if not _symbol_untouched(ref, changed, all_stems):
            return False
    return True


def _is_code(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def _stem(path: str) -> str:
    return Path(path).stem


def _changed_symbols(
    root: Path, anchor: str | None, hits: list[str]
) -> list[tuple[str, set[str] | None]]:
    """For each changed *code* hit: (module stem, changed symbols | None).

    ``None`` marks an opaque file (unparseable, deleted, or a code language we
    can't parse) — the caller reads it as "every symbol here might have moved".
    """
    hunks = gitutil.changed_hunks(root, anchor)
    resolved: list[tuple[str, set[str] | None]] = []
    for hit in hits:
        if not _is_code(hit):
            continue  # non-code changes can't touch a code symbol
        syms = symbols.changed_symbols(root / hit, hunks.get(hit, []))
        resolved.append((_stem(hit), syms))
    return resolved


def _symbol_untouched(
    ref: str, changed: list[tuple[str, set[str] | None]], all_stems: set[str]
) -> bool:
    """True only when the referenced symbol is *provably* untouched.

    ``ref`` is ``…qualifier.symbol``; the qualifier is the enclosing module or
    class. The symbol is touched when a changed file that could hold it either
    can't be parsed or lists the symbol among its changes. If no changed file
    can hold it, the symbol's file didn't change — provably untouched.
    """
    parts = ref.split(".")
    if len(parts) < 2:
        return False  # not a resolvable module.symbol — refuse to vouch
    symbol, qualifier = parts[-1], parts[-2]
    dotted = f"{qualifier}.{symbol}"
    for stem, syms in changed:
        if syms is None:
            # Opaque changed file. It could hold the symbol unless the ref
            # clearly names a *different*, known module.
            if stem == qualifier or qualifier not in all_stems:
                return False
            continue
        if stem == qualifier and symbol in syms:
            return False  # `module.symbol` — the referenced def changed here
        if dotted in syms:
            return False  # `Class.method` — the referenced method changed here
    if qualifier not in all_stems:
        # An unresolvable qualifier (not a known module, not a matched class):
        # if any changed file moved a symbol of this name, we can't prove ours
        # is a different one. Conservative — fall back to stale.
        for _stem_, syms in changed:
            if syms is not None and symbol in syms:
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
