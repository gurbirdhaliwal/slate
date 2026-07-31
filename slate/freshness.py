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

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import claims as claims_mod
from . import context, generator, gitutil, globs, scanner, symbols
from .context import CONTEXT_DOC_PATHS, FRESH, NEEDS_VERIFICATION, STALE, ContextDoc, load_all
from .refs import extract_path_refs, extract_symbol_refs
from .scanner import CODE_EXTENSIONS, RepoScan

# Per-claim verdicts (a finer grain than the doc-level status). "unknowable"
# is a claim whose reference can't be resolved to prove either way — an opaque
# file, an unresolvable symbol; it keeps the doc out of `fresh` just like a
# stale claim, but tells the reader "verify this by hand" rather than "this
# changed". fresh/stale reuse the doc-level constants.
CLAIM_FRESH = FRESH
CLAIM_STALE = STALE
CLAIM_UNKNOWABLE = "unknowable"
_CLAIM_SEVERITY = {CLAIM_FRESH: 0, CLAIM_UNKNOWABLE: 1, CLAIM_STALE: 2}


@dataclass
class ClaimVerdict:
    text: str                # the claim's display text
    section: str             # enclosing heading, for orientation
    kind: str                # "human" | "generated"
    status: str              # fresh | stale | unknowable
    refs: list[str] = field(default_factory=list)   # code refs that scope it
    risk: list[str] = field(default_factory=list)   # the refs that put it at risk

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "section": self.section,
            "kind": self.kind,
            "status": self.status,
            "refs": self.refs,
            "risk": self.risk,
        }


@dataclass
class DocReport:
    doc: ContextDoc
    status: str
    changed_watched: list[str] = field(default_factory=list)
    reason: str = ""
    # True when the status was established by comparing content (scan facts
    # or the watched-file digest) rather than by an all-quiet anchor diff.
    content_verified: bool = False
    # Per-claim breakdown (populated when watched paths changed). The doc-level
    # status is a conservative roll-up: `fresh` only if every claim is fresh.
    claims: list[ClaimVerdict] = field(default_factory=list)

    @property
    def rel_path(self) -> str:
        return self.doc.spec.rel_path

    @property
    def suspect_claims(self) -> list[ClaimVerdict]:
        return [c for c in self.claims if c.status != CLAIM_FRESH]


def evaluate_doc(root: Path, doc: ContextDoc, scan: RepoScan | None = None) -> DocReport:
    get_scan = (lambda: scan) if scan is not None else _scan_once(root)
    _GIT_ANSWERS.clear()
    return _evaluate(root, doc, get_scan)


def evaluate_all(root: Path) -> list[DocReport]:
    get_scan = _scan_once(root)  # at most one scan for the whole layer
    _GIT_ANSWERS.clear()
    return [_evaluate(root, doc, get_scan) for doc in load_all(root)]


# Authorship narrowing asks the same few questions many times over — the same
# file's last change, the same doc's blame, the same ancestry pair — once per
# ref per claim. Answers are pinned to one evaluation and dropped at the next,
# so a long-lived process (the MCP server) never reads a stale commit.
_GIT_ANSWERS: dict[tuple, object] = {}


def _once(key: tuple, compute: Callable[[], object]) -> object:
    if key not in _GIT_ANSWERS:
        _GIT_ANSWERS[key] = compute()
    return _GIT_ANSWERS[key]


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

    scan = get_scan()
    changed_syms = _changed_symbols(root, anchor, hits)
    all_stems = {_stem(f) for f in scan.files if _is_code(f)}
    claims = _build_claims(root, anchor, doc, hits, scan, changed_syms, all_stems)

    if _claims_still_check_out(root, anchor, doc, hits, scan, changed_syms, all_stems):
        return DocReport(
            doc, FRESH, changed_watched=hits, content_verified=True, claims=claims,
            reason=(
                f"{len(hits)} watched path(s) changed since {anchor}, but every claim "
                "the doc makes provably still checks out"
            ),
        )
    suspect = [c for c in claims if c.status != CLAIM_FRESH]
    detail = (
        f"{len(suspect)} of {len(claims)} claim(s) suspect"
        if claims else f"{len(hits)} watched path(s) changed"
    )
    return DocReport(
        doc, STALE, changed_watched=hits, claims=claims,
        reason=f"{detail} since {anchor}",
    )


def _claims_still_check_out(
    root: Path, anchor: str, doc: ContextDoc, hits: list[str], scan: RepoScan,
    changed_syms: list[tuple[str, set[str] | None]], all_stems: set[str],
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

    This is the authoritative doc-level roll-up: it scans the *whole* human
    text (not a segmentation of it), so a claim the segmenter might miss can
    never sneak the doc to `fresh`. It is provably equivalent to "every claim
    fresh" whenever segmentation is complete — the breakdown in ``_build_claims``
    is the finer-grained view, this is the safety net. A false "fresh" is the
    catastrophic bug (product doc §10); symbol resolution may only ever *narrow*
    stale→fresh, never the reverse.
    """
    # A doc with no auto-block has no generated facts to match; the prose
    # conditions below are then the whole test. (Before read-next became
    # watch-based nothing ungenerated ever reached here, so this returned
    # False outright — which made such a doc permanently stale.)
    if doc.spec.generated:
        current = context.get_auto_block(doc.body)
        if current is None:
            return False
        regenerated = generator.auto_content(doc.spec, scan)
        if current != regenerated and not current.endswith("\n\n" + regenerated):
            return False
    human_text = _human_text(doc.body)

    # A claim about a whole file (a path reference) can't be narrowed by symbol
    # resolution — any edit inside it might touch what the claim depends on.
    # It *can* be narrowed by authorship: prose written at or after the change
    # was written against it.
    for ref in extract_path_refs(human_text):
        for hit in hits:
            if hit == ref or hit.startswith(ref + "/"):
                if _prose_supersedes(root, doc, _ref_lines(doc.body, ref), [ref], anchor):
                    continue
                return False

    for ref in extract_symbol_refs(human_text):
        if _symbol_verdict(ref, changed_syms, all_stems) != CLAIM_FRESH:
            if _prose_supersedes(
                root, doc, _ref_lines(doc.body, ref), _symbol_files(ref, hits), anchor
            ):
                continue
            return False
    return True


def _human_text(body: str) -> str:
    begin = body.find(context.AUTO_BEGIN)
    if begin == -1:
        return body
    end = body.find(context.AUTO_END) + len(context.AUTO_END)
    return body[:begin] + body[end:]


def _ref_lines(body: str, ref: str) -> list[int]:
    """1-based body lines that mention `ref`."""
    return [n for n, line in enumerate(body.splitlines(), 1) if ref in line]


def _symbol_files(ref: str, hits: list[str]) -> list[str]:
    """Changed code files that could host a ``module.symbol`` reference.

    A resolvable qualifier names one file. Anything else (an unknown module, a
    ``Class.method`` whose file we can't name) yields *every* changed code
    file, mirroring `_symbol_verdict`'s own conservatism: the prose must then
    be newer than all of them before it can narrow.
    """
    parts = ref.split(".")
    if len(parts) < 2:
        return []
    code = [hit for hit in hits if _is_code(hit)]
    return [hit for hit in code if _stem(hit) == parts[-2]] or code


def _prose_supersedes(
    root: Path, doc: ContextDoc, body_lines: list[int], refs: list[str], anchor: str
) -> bool:
    """True when this prose was written at or after every change in `refs`.

    Prose and code that land in the same commit are not doc rot: the author
    wrote the sentence against the change. Without this, a claim is flagged the
    moment the doc's anchor predates the commit that introduced *both* — which
    was the largest false-positive class this repo has ever produced.

    Narrowing only, in the same sense as symbol resolution: every question we
    cannot answer returns False, so the claim keeps whatever verdict it had.
    """
    if not body_lines or not refs:
        return False
    blamed = _once(
        ("blame", doc.spec.rel_path),
        lambda: gitutil.blame_lines(root, doc.spec.rel_path),
    )
    if not isinstance(blamed, dict):
        return False
    file_lines = [doc.body_line + n - 1 for n in body_lines]
    if any(n not in blamed for n in file_lines):
        return False  # a line blame can't place — decline rather than guess
    written = {blamed[n] for n in file_lines}
    for ref in refs:
        code_commit = _once(
            ("last-change", ref, anchor),
            lambda ref=ref: gitutil.last_change_commit(root, ref, anchor),
        )
        if code_commit is None:
            # Nothing committed since the anchor touched it, yet it is among
            # the hits — so the change is working-tree-only, and only
            # working-tree prose can have been written against it.
            if any(sha != gitutil.UNCOMMITTED for sha in written):
                return False
            continue
        if any(
            sha != gitutil.UNCOMMITTED
            and not _once(
                ("ancestor", code_commit, sha),
                lambda c=code_commit, s=sha: gitutil.is_ancestor(root, c, s),
            )
            for sha in written
        ):
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


def _symbol_verdict(
    ref: str, changed: list[tuple[str, set[str] | None]], all_stems: set[str]
) -> str:
    """Classify a ``module.symbol`` reference against the change.

    ``ref`` is ``…qualifier.symbol``; the qualifier is the enclosing module or
    class. Returns:

    - ``stale`` — a changed file provably moved the referenced symbol;
    - ``unknowable`` — a file that could hold it can't be parsed, or the
      qualifier is unresolvable and a same-named symbol moved somewhere, so we
      can't prove it's a different one (verify by hand);
    - ``fresh`` — no changed file can hold it, or the file changed elsewhere.

    ``stale`` and ``unknowable`` both keep the doc out of `fresh`; only ``fresh``
    lets the doc-level roll-up vouch for the claim.
    """
    parts = ref.split(".")
    if len(parts) < 2:
        return CLAIM_UNKNOWABLE  # not a resolvable module.symbol — refuse to vouch
    symbol, qualifier = parts[-1], parts[-2]
    dotted = f"{qualifier}.{symbol}"
    verdict = CLAIM_FRESH
    for stem, syms in changed:
        if syms is None:
            # Opaque changed file. It could hold the symbol unless the ref
            # clearly names a *different*, known module.
            if stem == qualifier or qualifier not in all_stems:
                verdict = _worse(verdict, CLAIM_UNKNOWABLE)
            continue
        if stem == qualifier and symbol in syms:
            return CLAIM_STALE  # `module.symbol` — the referenced def changed here
        if dotted in syms:
            return CLAIM_STALE  # `Class.method` — the referenced method changed here
    if qualifier not in all_stems:
        # An unresolvable qualifier (not a known module, not a matched class):
        # if any changed file moved a symbol of this name, we can't prove ours
        # is a different one. Conservative — unknowable, never fresh.
        for _stem_, syms in changed:
            if syms is not None and symbol in syms:
                verdict = _worse(verdict, CLAIM_UNKNOWABLE)
    return verdict


def _worse(a: str, b: str) -> str:
    return a if _CLAIM_SEVERITY[a] >= _CLAIM_SEVERITY[b] else b


def _build_claims(
    root: Path, anchor: str, doc: ContextDoc, hits: list[str], scan: RepoScan,
    changed_syms: list[tuple[str, set[str] | None]], all_stems: set[str],
) -> list[ClaimVerdict]:
    """The per-claim breakdown behind the doc-level status (presentation/score).

    Generated facts get a line-level verdict against a fresh scan; human claims
    get the same symbol/path resolution the roll-up uses, so the two can't
    disagree on any reference they both see.
    """
    return _generated_claims(doc, scan) + _human_claim_verdicts(
        root, anchor, doc, hits, changed_syms, all_stems
    )


def _generated_claims(doc: ContextDoc, scan: RepoScan) -> list[ClaimVerdict]:
    if not doc.spec.generated:
        return []
    current = context.get_auto_block(doc.body)
    regenerated = generator.auto_content(doc.spec, scan)
    if current is None:
        return [ClaimVerdict(
            "auto-block markers missing", "(generated)", "generated",
            CLAIM_STALE, risk=["auto-block boundary"],
        )]
    facts = current
    if current != regenerated and current.endswith("\n\n" + regenerated):
        facts = regenerated  # an LLM prose prefix isn't a fact — score the facts

    on_disk = facts.splitlines()
    fresh_scan = regenerated.splitlines()
    out: list[ClaimVerdict] = []
    matcher = difflib.SequenceMatcher(None, on_disk, fresh_scan, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out += [_gen_claim(line, CLAIM_FRESH) for line in on_disk[i1:i2] if _is_fact_line(line)]
            continue
        # A line the fresh scan drops or rewrites — the fact on disk is suspect.
        out += [_gen_claim(line, CLAIM_STALE, "sync would rewrite this line")
                for line in on_disk[i1:i2] if _is_fact_line(line)]
        # A line the fresh scan adds — a new fact (e.g. a crossed module
        # boundary) the doc doesn't state yet.
        out += [_gen_claim(line, CLAIM_STALE, "sync would add this line")
                for line in fresh_scan[j1:j2] if _is_fact_line(line)]
    return out


def _gen_claim(line: str, status: str, risk: str = "") -> ClaimVerdict:
    return ClaimVerdict(
        line.strip(), "(generated facts)", "generated", status,
        refs=extract_path_refs(line), risk=[risk] if risk else [],
    )


def _is_fact_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # Table separators and horizontal rules carry no claim.
    return not set(stripped) <= set("|-: ")


def _human_claim_verdicts(
    root: Path, anchor: str, doc: ContextDoc, hits: list[str],
    changed_syms: list[tuple[str, set[str] | None]], all_stems: set[str],
) -> list[ClaimVerdict]:
    out: list[ClaimVerdict] = []
    for claim in claims_mod.human_claims(doc.body):
        status = CLAIM_FRESH
        risk: list[str] = []
        for ref in claim.path_refs:
            if any(hit == ref or hit.startswith(ref + "/") for hit in hits):
                if _prose_supersedes(root, doc, claim.lines, [ref], anchor):
                    continue
                status = CLAIM_STALE
                risk.append(ref)
        for ref in claim.symbol_refs:
            verdict = _symbol_verdict(ref, changed_syms, all_stems)
            if verdict != CLAIM_FRESH:
                if _prose_supersedes(
                    root, doc, claim.lines, _symbol_files(ref, hits), anchor
                ):
                    continue
                status = _worse(status, verdict)
                risk.append(ref)
        out.append(ClaimVerdict(
            claim.text, claim.section, "human", status, refs=claim.refs, risk=risk,
        ))
    return out


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
