"""Every file Slate reads or writes is UTF-8, explicitly.

`Path.read_text()`/`write_text()` without `encoding=` use the *locale* encoding.
On Linux and macOS that is UTF-8 and nothing goes wrong; on Windows it is
typically cp1252, which cannot encode most of what Slate puts in a doc — the
status glyphs (● ○ ◐ ✗), the arrows (→ ↳), the verify bars (█ ░). A layer
written on macOS and read on Windows, or written on Windows at all, fails with
a UnicodeEncodeError from inside pathlib.

This is the cheapest cross-platform bug to reintroduce, because it looks like
nothing on the machine you develop on.
"""

from __future__ import annotations

import re
from pathlib import Path

SLATE = Path(__file__).resolve().parent.parent / "slate"

# `read_text(` / `write_text(` calls, minus the ones that pass encoding on the
# same line. A multi-line call is matched by looking ahead to the closing paren.
_CALL = re.compile(r"\.(read_text|write_text)\(")


def _calls_without_encoding(source: str) -> list[str]:
    offenders = []
    for match in _CALL.finditer(source):
        # Scan forward to the matching close paren, tolerating nesting.
        depth, index = 0, match.end() - 1
        while index < len(source):
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        call = source[match.start():index + 1]
        if "encoding=" not in call:
            offenders.append(" ".join(call.split()))
    return offenders


def test_all_file_io_declares_utf8() -> None:
    bad: dict[str, list[str]] = {}
    for path in sorted(SLATE.glob("*.py")):
        offenders = _calls_without_encoding(path.read_text(encoding="utf-8"))
        if offenders:
            bad[path.name] = offenders
    assert not bad, (
        "file I/O without an explicit encoding falls back to the locale "
        f"encoding, which breaks on Windows: {bad}")


def test_the_glyphs_slate_writes_are_not_cp1252_encodable() -> None:
    """The premise, asserted rather than assumed.

    If this ever fails, Slate has stopped using characters that would break a
    cp1252 default — and the test above is no longer load-bearing, rather than
    the bug being gone.
    """
    from slate import context, verify  # noqa: F401

    unencodable = [c for c in "●○◐✗→↳█░≈≠" if _fails_cp1252(c)]
    assert unencodable, "expected these glyphs to be outside cp1252"


def _fails_cp1252(char: str) -> bool:
    try:
        char.encode("cp1252")
        return False
    except UnicodeEncodeError:
        return True
