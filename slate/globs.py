"""Watch-pattern matching.

Context docs declare *watch globs* — the code paths whose changes can
invalidate them. Python's fnmatch has no ``**`` semantics, so patterns are
compiled to regexes by hand:

    **/   any number of leading directories (including none)
    **    anything, across directory boundaries
    *     anything within one path segment
    ?     one character within a segment

Paths are always repo-relative POSIX paths.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
            elif pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(pattern: str, path: str) -> bool:
    return _compile(pattern).match(path) is not None


def any_match(patterns: list[str], path: str) -> bool:
    return any(matches(p, path) for p in patterns)


def filter_paths(patterns: list[str], paths: list[str]) -> list[str]:
    return [p for p in paths if any_match(patterns, p)]
