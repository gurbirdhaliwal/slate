"""References a doc body makes — to repo paths, and to code symbols.

Context docs claim things about two kinds of target: *paths* (markdown links
and backticked file paths) and *symbols* (a backticked ``module.symbol`` like
``context.get_auto_block``). The verification score needs the paths (do they
still exist?); the freshness engine needs both — a changed path can invalidate
a whole-file claim, and a changed *symbol* can invalidate a claim that names it
even when the coarse scan can't see the difference. Both extractions live here,
below every caller.
"""

from __future__ import annotations

import re

# Path-like tokens: markdown link targets and backticked segments with a "/",
# or well-known root files. Anchors/URLs are excluded.
_LINK = re.compile(r"\]\(([^)#\s]+)\)")
_TICKED = re.compile(r"`([A-Za-z0-9_./-]+)`")
_ROOT_FILES = {"Makefile", "README.md", "pyproject.toml", "package.json", "pom.xml"}

# Symbol tokens: a backticked dotted chain of identifiers, `module.symbol` or
# `module.Class.method`. No slash (that's a path) and each part is a real
# identifier, so filenames and version strings don't sneak in.
_SYMBOL = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")
# Final components that mark the token as a filename, not a symbol reference.
_FILE_EXTENSIONS = {
    "py", "js", "jsx", "ts", "tsx", "json", "md", "toml", "yml", "yaml",
    "txt", "cfg", "ini", "lock", "png", "svg", "sh", "html", "css",
}


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


def extract_symbol_refs(body: str) -> list[str]:
    """Backticked ``module.symbol`` references a claim makes (paths excluded)."""
    refs: set[str] = set()
    for match in _SYMBOL.finditer(body):
        token = match.group(1)
        if token.rsplit(".", 1)[-1].lower() in _FILE_EXTENSIONS:
            continue  # `foo.py`, `config.json` — a filename, not a symbol
        refs.add(token)
    return sorted(refs)
