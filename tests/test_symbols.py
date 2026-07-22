"""Symbol resolution and hunk parsing — against real files and real git repos.

These are the deterministic building blocks the freshness engine narrows on;
the false-fresh guard lives one layer up, but everything here is exercised
against genuine `git diff` output rather than hand-built fixtures.
"""

from __future__ import annotations

from pathlib import Path

from slate import gitutil, symbols

from .conftest import commit_all, git

SAMPLE = '''\
"""Module docstring."""

CONSTANT = 1


def alpha():
    return 1


def beta(x):
    # a comment
    return x + 1


class Widget:
    kind = "gear"

    def spin(self):
        return "spin"

    def stop(self):
        return "stop"
'''


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(text)
    return path


def test_range_inside_one_function_resolves_to_it(tmp_path: Path) -> None:
    path = write(tmp_path, SAMPLE)
    # `beta` spans lines 10-12; a change on line 12 is beta, nothing else.
    assert symbols.changed_symbols(path, [(12, 12)]) == {"beta"}


def test_module_docstring_change_touches_no_symbol(tmp_path: Path) -> None:
    path = write(tmp_path, SAMPLE)
    assert symbols.changed_symbols(path, [(1, 1)]) == set()


def test_module_level_assignment_is_a_symbol(tmp_path: Path) -> None:
    path = write(tmp_path, SAMPLE)
    assert symbols.changed_symbols(path, [(3, 3)]) == {"CONSTANT"}


def test_method_reports_qualified_bare_and_class(tmp_path: Path) -> None:
    path = write(tmp_path, SAMPLE)
    # `spin` body is line 19; a claim may reference it as spin, Widget.spin,
    # or the whole Widget — all three must match.
    changed = symbols.changed_symbols(path, [(19, 19)])
    assert changed == {"spin", "Widget.spin", "Widget"}


def test_class_attribute_change_reports_class(tmp_path: Path) -> None:
    path = write(tmp_path, SAMPLE)
    changed = symbols.changed_symbols(path, [(16, 16)])  # kind = "gear"
    assert "Widget" in changed and "kind" in changed


def test_unparseable_python_is_opaque(tmp_path: Path) -> None:
    path = write(tmp_path, "def broken(:\n    pass\n")
    assert symbols.changed_symbols(path, [(1, 1)]) is None


def test_unknown_code_language_is_opaque(tmp_path: Path) -> None:
    path = tmp_path / "main.go"
    path.write_text("package main\nfunc main() {}\n")
    assert symbols.changed_symbols(path, [(2, 2)]) is None


def test_missing_file_is_opaque(tmp_path: Path) -> None:
    assert symbols.changed_symbols(tmp_path / "gone.py", [(1, 1)]) is None


def test_js_top_level_declarations(tmp_path: Path) -> None:
    path = tmp_path / "app.js"
    path.write_text(
        "export function activate() {\n"
        "  return 1;\n"
        "}\n"
        "\n"
        "const helper = () => 2;\n"
    )
    assert symbols.changed_symbols(path, [(2, 2)]) == {"activate"}
    assert symbols.changed_symbols(path, [(5, 5)]) == {"helper"}


# --- hunk parsing against real git diffs ------------------------------------


def test_changed_hunks_committed_edit(repo: Path) -> None:
    anchor = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "edit engine")
    hunks = gitutil.changed_hunks(repo, anchor)
    assert "demo/engine.py" in hunks
    # Line 2 (`return`) changed; the range must cover it.
    assert any(start <= 2 <= end for start, end in hunks["demo/engine.py"])


def test_changed_hunks_includes_uncommitted_edit(repo: Path) -> None:
    anchor = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "demo" / "engine.py").write_text("def run():\n    return 44\n")  # not committed
    hunks = gitutil.changed_hunks(repo, anchor)
    assert "demo/engine.py" in hunks


def test_changed_hunks_untracked_file_reported_whole(repo: Path) -> None:
    anchor = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "demo" / "widget.py").write_text("a = 1\nb = 2\nc = 3\n")
    hunks = gitutil.changed_hunks(repo, anchor)
    assert hunks["demo/widget.py"] == [(1, 4)]  # 3 lines + trailing newline
