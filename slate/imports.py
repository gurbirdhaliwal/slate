"""Watch inference — propose watch globs from import graphs.

Default watches come from directory heuristics at init time; they drift as
the codebase grows (a new top-level package appears, a doc starts talking
about paths it doesn't watch). This module proposes *additions*, from two
deterministic signals:

  1. Import edges: if a watched directory imports from an unwatched
     directory, changes there can invalidate the doc too. Python and JS/TS
     imports are parsed by regex — deliberately shallow (no resolver) — but
     resolved against the repo's actual package layout, so a ``src/<pkg>/``
     project yields a real graph rather than an empty one. Suggestions are
     still widened to top-level globs before being proposed.
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
_PY_RELATIVE = re.compile(r"^\s*from\s+(\.+)([\w.]*)\s+import", re.M)
_JS_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]""")

_PY_SUFFIXES = {".py"}
_JS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}


@dataclass(frozen=True)
class Suggestion:
    pattern: str
    reason: str


def import_edges(scan: RepoScan) -> dict[str, set[str]]:
    """module path -> set of other module paths it imports from."""
    return compute_edges(scan.root, scan.files, scan.module_paths)


def compute_edges(
    root: Path, files: list[str], module_paths: list[str]
) -> dict[str, set[str]]:
    """The module-level dependency graph, from primitives (no RepoScan needed).

    Split out so ``scanner`` can compute edges *while building* a scan without
    an import cycle, and so the graph is parsed in exactly one place — watch
    inference (``import_edges``) and the tracked-fact renderer share it.

    Import *names* are resolved to directories rather than matched against
    first path segments: under a ``src/`` layout ``from flask.json import x``
    names no directory called ``flask``, so segment matching finds nothing and
    the graph comes back empty on most real repos.
    """
    owner = _owner_fn(module_paths)
    packages = _package_index(files)
    edges: dict[str, set[str]] = {m: set() for m in module_paths}
    for rel in files:
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix not in _PY_SUFFIXES | _JS_SUFFIXES:
            continue
        source = owner(_dirname(rel))
        if source is None:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        targets = (
            _python_targets(text, rel, packages)
            if suffix in _PY_SUFFIXES
            else _js_targets(text, rel)
        )
        for target in targets:
            resolved = owner(target)
            if resolved is not None and resolved != source:
                edges[source].add(resolved)
    return edges


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _owner_fn(module_paths: list[str]):
    """Map a directory to the most specific module that contains it."""
    ranked = sorted(module_paths, key=len, reverse=True)

    def owner(directory: str) -> str | None:
        for module in ranked:
            if directory == module or directory.startswith(module + "/"):
                return module
        return None

    return owner


def _package_index(files: list[str]) -> dict[str, str]:
    """Dotted import name -> directory, for every importable dir in the repo.

    A package's importable name is its path relative to the highest ancestor
    that is *not* itself a package — which is what makes ``src/flask/json``
    importable as ``flask.json`` and keeps ``src`` out of the name.

    Plain top-level directories (no ``__init__.py``, e.g. a ``lib/`` of loose
    modules) are indexed by their own name as a fallback. That fallback is
    deliberately confined to depth 1: indexing every nested directory by its
    basename would make a vendored ``src/flask/json/`` swallow ``import json``
    and invent an edge that does not exist.
    """
    package_dirs = {
        _dirname(f) for f in files if f.endswith("/__init__.py") or f == "__init__.py"
    }
    index: dict[str, str] = {}
    for directory in sorted(package_dirs):
        if directory == ".":
            continue
        parts = directory.split("/")
        cut = len(parts) - 1
        while cut > 0 and "/".join(parts[:cut]) in package_dirs:
            cut -= 1
        index.setdefault(".".join(parts[cut:]), directory)
    for path in sorted(files):
        parent = _dirname(path)
        if "/" not in parent and parent != ".":
            index.setdefault(parent, parent)
    return index


def _python_targets(text: str, rel: str, packages: dict[str, str]) -> set[str]:
    """Directories named by this file's imports, absolute and relative."""
    targets: set[str] = set()
    for match in _PY_IMPORT.finditer(text):
        resolved = _resolve_dotted(match.group(1), packages)
        if resolved is not None:
            targets.add(resolved)
    here = _dirname(rel)
    for match in _PY_RELATIVE.finditer(text):
        parts = here.split("/")
        up = len(match.group(1)) - 1  # a single dot is "this package"
        base = "/".join(parts[: len(parts) - up]) if up <= len(parts) else ""
        if not base:
            continue
        tail = match.group(2).split(".")[0] if match.group(2) else ""
        targets.add(f"{base}/{tail}" if tail else base)
    return targets


def _resolve_dotted(dotted: str, packages: dict[str, str]) -> str | None:
    """Longest dotted prefix that names a package in this repo, as a directory."""
    parts = dotted.split(".")
    for stop in range(len(parts), 0, -1):
        directory = packages.get(".".join(parts[:stop]))
        if directory is not None:
            return directory
    return None


def _js_targets(text: str, rel: str) -> set[str]:
    targets: set[str] = set()
    file_dir = PurePosixPath(rel).parent
    for m in _JS_IMPORT.finditer(text):
        spec = m.group(1)
        if not spec.startswith("."):
            continue  # bare package names are dependencies, not repo dirs
        resolved = _normalize(file_dir / spec)
        if resolved:
            targets.add(_dirname(resolved) if "." in PurePosixPath(resolved).name
                        else resolved)
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
    # Watches are top-level (see RepoScan.source_dirs), so the module-path edge
    # graph is projected back up before comparing: a suggestion must widen the
    # net, and `src/flask/**` would narrow it.
    if doc.spec.generated:
        watched_dirs = {w[: -len("/**")] for w in watches if w.endswith("/**")}
        top_edges: dict[str, set[str]] = {}
        for source, deps in edges.items():
            top = source.split("/", 1)[0]
            top_edges.setdefault(top, set()).update(d.split("/", 1)[0] for d in deps)
        for src in sorted(watched_dirs & set(top_edges)):
            for dep in sorted(top_edges[src] - {src}):
                if not covered(dep):
                    suggestions.setdefault(
                        f"{dep}/**",
                        Suggestion(f"{dep}/**", f"`{src}/` imports from `{dep}/`"),
                    )

    # Signal 2 — paths the doc body references (any doc).
    from .refs import extract_path_refs

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
