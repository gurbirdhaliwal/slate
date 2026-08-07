"""Every file Slate reads or writes is UTF-8, explicitly.

`Path.read_text()`/`write_text()` without `encoding=` use the *locale* encoding.
On Linux and macOS that is UTF-8 and nothing goes wrong; on Windows it is
typically cp1252, which cannot encode most of what Slate puts in a doc — the
status glyphs (● ○ ◐ ✗), the arrows (→ ↳), the verify bars (█ ░).

This guard is written against the AST, not the source text, and that is the
whole point. The first version matched the string `encoding=` anywhere in the
call and so was fooled by a *nested* call supplying its own:

    read_next.write_text(read_next.read_text(encoding="utf-8") + more)

The write there has no encoding of its own. On Windows it wrote cp1252 while
every reader had been fixed to expect UTF-8, which turned a silent mojibake bug
into 53 hard `UnicodeDecodeError` failures — worse than before the fix. Only the
parsed keyword list can tell the two apart.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("slate", "tests", "benchmarks")


def _sources() -> list[Path]:
    # `.work/` is gitignored scratch — cloned upstream repos and a venv. Their
    # I/O is not ours to police, and scanning it made this guard fail on pip.
    return [p for tree in TREES for p in (ROOT / tree).rglob("*.py")
            if ".work" not in p.parts]


def _calls_without_encoding(source: str) -> list[str]:
    """`.read_text(...)`/`.write_text(...)` lacking their *own* encoding kwarg."""
    try:
        tree = ast.parse(source)
    except SyntaxError:  # reported by the compile check, not this one
        return []
    return [
        f"line {node.lineno}: .{node.func.attr}(...)"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("read_text", "write_text")
        and not any(kw.arg == "encoding" for kw in node.keywords)
    ]


def test_all_file_io_declares_utf8() -> None:
    bad = {}
    for path in sorted(_sources()):
        offenders = _calls_without_encoding(path.read_text(encoding="utf-8"))
        if offenders:
            bad[str(path.relative_to(ROOT))] = offenders
    assert not bad, (
        "file I/O without its own explicit encoding falls back to the locale "
        f"encoding, which breaks on Windows: {bad}")


def test_every_source_file_parses() -> None:
    """Catches the 3.11-invalid f-string nesting a bulk edit can introduce.

    PEP 701 lets 3.12+ reuse a quote character inside an f-string
    interpolation; 3.11 rejects it. A rewrite that produced
    `f"{p.read_text(encoding="utf-8")}"` therefore passed locally on a new
    interpreter and was a SyntaxError in CI.
    """
    broken = []
    for path in sorted(_sources()):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            broken.append(f"{path.relative_to(ROOT)}: {exc}")
    assert not broken, broken


def test_the_glyphs_slate_writes_are_not_cp1252_encodable() -> None:
    """The premise, asserted rather than assumed.

    If this fails, Slate stopped using characters cp1252 cannot encode — and
    the guard above is no longer load-bearing, rather than the bug being gone.
    """
    unencodable = [c for c in "●○◐✗→↳█░≈≠" if _fails_cp1252(c)]
    assert unencodable, "expected these glyphs to be outside cp1252"


def _fails_cp1252(char: str) -> bool:
    try:
        char.encode("cp1252")
        return False
    except UnicodeEncodeError:
        return True
