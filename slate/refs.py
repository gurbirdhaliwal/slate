"""Path references a doc body makes.

Context docs claim things about repo paths — markdown links and backticked
paths. Both the verification score (do the paths still exist?) and the
freshness engine (did a changed path touch a hand-written claim?) need the
same extraction, so it lives here, below both.
"""

from __future__ import annotations

import re

# Path-like tokens: markdown link targets and backticked segments with a "/",
# or well-known root files. Anchors/URLs are excluded.
_LINK = re.compile(r"\]\(([^)#\s]+)\)")
_TICKED = re.compile(r"`([A-Za-z0-9_./-]+)`")
_ROOT_FILES = {"Makefile", "README.md", "pyproject.toml", "package.json", "pom.xml"}


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
