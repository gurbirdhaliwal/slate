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
import subprocess
from pathlib import Path

import pytest

from .conftest import commit_all

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


# --------------------------------------------------------------------------
# git's output is not the locale's business
#
# Windows CI died here: `subprocess.run(text=True)` decodes with the *locale*
# codec, so the first non-ASCII byte of a diff killed the reader thread and
# `run` returned stdout=None. The crash was the lucky outcome — an empty diff
# reads as "no symbols changed", which narrows stale→fresh (product doc §10).


def _subprocess_calls_without_encoding(source: str) -> list[str]:
    """`subprocess.run(..., text=True)` calls that never pin an encoding."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "run":
            continue
        kwargs = {kw.arg for kw in node.keywords}
        if "text" in kwargs and "encoding" not in kwargs:
            bad.append(f"line {node.lineno}: subprocess.run(text=True) with no encoding=")
    return bad


def test_git_output_is_never_decoded_with_the_locale_codec() -> None:
    offenders = {
        path.name: bad
        for path in (Path(__file__).resolve().parent.parent / "slate").rglob("*.py")
        if (bad := _subprocess_calls_without_encoding(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        "text=True decodes with the locale codec (cp1252 on Windows); "
        f"pin encoding='utf-8': {offenders}"
    )


def test_a_non_ascii_diff_still_reports_its_hunks(tmp_path: Path) -> None:
    """A diff full of UTF-8 must survive the trip out of git.

    Note this passes on POSIX either way — the locale there is already UTF-8.
    It earns its keep on Windows, where the pre-fix code returned stdout=None
    and this assertion is the difference between a caught drift and a blessed
    doc. The platform-independent guard is the AST test above.
    """
    from slate import gitutil

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    src = root / "mod.py"
    src.write_text("def a():\n    return 1\n", encoding="utf-8")
    commit_all(root, "init")
    base = gitutil.head_commit(root)
    src.write_text('def a():\n    """cost \u2248 0.09 \u2014 cheap."""\n    return 2\n',
                   encoding="utf-8")
    commit_all(root, "touch a")

    hunks = gitutil.changed_hunks(root, base)

    assert "mod.py" in hunks, (
        "a non-ASCII diff vanished — the freshness engine would see no "
        "changed symbols and call the doc fresh"
    )


def test_git_output_that_cannot_be_read_raises_rather_than_looking_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows failure mode: subprocess's reader thread dies, stdout=None.

    An empty diff and a diff we failed to read are indistinguishable to every
    caller downstream, and one of them means "nothing changed". Slate must
    stop instead of narrowing stale->fresh on a decode it never performed.
    """
    from slate import gitutil

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(root, "init")

    class _Dead:
        returncode = 0
        stdout = None          # what run() hands back when the reader thread dies
        stderr = ""

    monkeypatch.setattr(gitutil.subprocess, "run", lambda *a, **k: _Dead())
    with pytest.raises(gitutil.GitError):
        gitutil.changed_hunks(root, "HEAD")
