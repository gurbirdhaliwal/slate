"""Watch inference — propose watch globs from import graphs.

Default watches come from directory heuristics at init time; they drift as
the codebase grows (a new top-level package appears, a doc starts talking
about paths it doesn't watch). This module proposes *additions*, from two
deterministic signals:

  1. Import edges: if a watched directory imports from an unwatched
     top-level directory, changes there can invalidate the doc too.
     Python and JS/TS imports are parsed by regex — deliberately shallow
     (no resolver): top-level-directory granularity only.
  2. Body references: a human-owned doc that mentions paths under an
     unwatched directory probably depends on it.

Proposals are suggestions, never silently applied — under-watching is a
correctness risk the human should sign off on (`slate watches --apply`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import globs
from .context import ContextDoc
from .scanner import RepoScan

_PY_IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.M)
_JS_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]""")

_PY_SUFFIXES = {".py"}
_JS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}


@dataclass(frozen=True)
class Suggestion:
    pattern: str
    reason: str


def import_edges(scan: RepoScan) -> dict[str, set[str]]:
    """top-level dir -> set of other top-level dirs it imports from."""
    top_dirs = set(scan.source_dirs)
    edges: dict[str, set[str]] = {d: set() for d in top_dirs}
    for rel in scan.files:
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix not in _PY_SUFFIXES | _JS_SUFFIXES or "/" not in rel:
            continue
        top = rel.split("/", 1)[0]
        if top not in top_dirs:
            continue
        try:
            text = (scan.root / rel).read_text(errors="ignore")
        except OSError:
            continue
        targets = (
            _python_targets(text, top_dirs)
            if suffix in _PY_SUFFIXES
            else _js_targets(text, rel, top_dirs)
        )
        edges[top].update(t for t in targets if t != top)
    return edges


def _python_targets(text: str, top_dirs: set[str]) -> set[str]:
    return {
        m.group(1).split(".", 1)[0]
        for m in _PY_IMPORT.finditer(text)
        if m.group(1).split(".", 1)[0] in top_dirs
    }


def _js_targets(text: str, rel: str, top_dirs: set[str]) -> set[str]:
    targets: set[str] = set()
    file_dir = PurePosixPath(rel).parent
    for m in _JS_IMPORT.finditer(text):
        spec = m.group(1)
        if not spec.startswith("."):
            continue  # bare package names are dependencies, not repo dirs
        resolved = _normalize(file_dir / spec)
        top = resolved.split("/", 1)[0] if resolved else ""
        if top in top_dirs:
            targets.add(top)
    return targets


def _normalize(path: PurePosixPath) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def suggest(root: Path, doc: ContextDoc, scan: RepoScan,
            edges: dict[str, set[str]] | None = None) -> list[Suggestion]:
    """Watch-glob additions for one doc, deduped against current coverage."""
    if edges is None:
        edges = import_edges(scan)
    watches = doc.watches
    suggestions: dict[str, Suggestion] = {}

    def covered(directory: str) -> bool:
        # A dir is covered if its glob is present or some file in it already
        # matches an existing watch pattern.
        probe = f"{directory}/x"
        return f"{directory}/**" in watches or globs.any_match(watches, probe)

    # Signal 1 — import edges out of watched directories (generated docs).
    if doc.spec.generated:
        watched_dirs = {w[: -len("/**")] for w in watches if w.endswith("/**")}
        for src in sorted(watched_dirs & set(edges)):
            for dep in sorted(edges[src]):
                if not covered(dep):
                    suggestions.setdefault(
                        f"{dep}/**",
                        Suggestion(f"{dep}/**", f"`{src}/` imports from `{dep}/`"),
                    )

    # Signal 2 — paths the doc body references (any doc).
    from .verify import extract_path_refs  # local import: verify imports nothing from here

    for ref in extract_path_refs(doc.body):
        if not (root / ref).exists() or "/" not in ref:
            continue
        top = ref.split("/", 1)[0]
        if top in scan.source_dirs and not covered(top):
            suggestions.setdefault(
                f"{top}/**",
                Suggestion(f"{top}/**", f"doc references `{ref}`"),
            )
    return list(suggestions.values())
