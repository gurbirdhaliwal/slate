"""Module discovery under a `src/<package>/` layout.

Keying the module map on the first path segment collapses this layout — the
most common one in Python, and near-universal in JS/TS — into a single `src/`
row, and leaves the dependency graph empty because `from flask.json import x`
names no directory called `flask`. Slate's own repo is flat (`slate/`,
`tests/`), so nothing in the dogfooded suite exercises this shape; these tests
do, against fixtures built to mirror the real repos that exposed it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slate import context, imports, scanner

from .conftest import commit_all, git


@pytest.fixture
def src_repo(tmp_path: Path) -> Path:
    """A repo shaped like Flask: package under src/, sub-packages, tests."""
    root = tmp_path / "webfx"
    root.mkdir()
    git(root, "init", "-q")
    (root / "README.md").write_text("# webfx\n")
    (root / "pyproject.toml").write_text('[project]\nname = "webfx"\nversion = "0.1"\n')

    pkg = root / "src" / "webfx"
    (pkg / "json").mkdir(parents=True)
    (pkg / "sansio").mkdir()
    (pkg / "__init__.py").write_text("from .app import App\n")
    (pkg / "app.py").write_text(
        "from .json.provider import Provider\nfrom .sansio.base import Base\n"
    )
    (pkg / "cli.py").write_text("def main():\n    return 0\n")
    (pkg / "globals.py").write_text("current_app = None\n")
    (pkg / "json" / "__init__.py").write_text("from ..globals import current_app\n")
    (pkg / "json" / "provider.py").write_text("import json\n\nclass Provider: ...\n")
    (pkg / "sansio" / "__init__.py").write_text("")
    (pkg / "sansio" / "base.py").write_text("class Base: ...\n")

    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text("from webfx.json.provider import Provider\n")

    commit_all(root, "initial")
    return root


def modules_of(repo: Path) -> dict[str, scanner.Module]:
    return {m.name: m for m in scanner.scan(repo).modules}


def test_package_under_src_gets_its_own_row(src_repo: Path) -> None:
    # The bug: a single `src` row, identical whether the package holds 5 files
    # or 500. The map must name the package the code actually lives in.
    names = modules_of(src_repo)
    assert "src/webfx" in names
    assert "src" not in names


def test_substantial_subpackages_are_broken_out(src_repo: Path) -> None:
    names = modules_of(src_repo)
    assert "src/webfx/json" in names  # 2 files — at the threshold
    assert "src/webfx/sansio" in names


def test_row_counts_partition_the_files(src_repo: Path) -> None:
    # Each file belongs to exactly one row, so a parent does not re-count what
    # a broken-out child already reports.
    mods = modules_of(src_repo)
    assert mods["src/webfx"].file_count == 4  # __init__, app, cli, globals
    assert mods["src/webfx/json"].file_count == 2
    assert mods["src/webfx/sansio"].file_count == 2


def test_entry_hints_survive_the_descent(src_repo: Path) -> None:
    assert modules_of(src_repo)["src/webfx"].entry_hints == ["src/webfx/cli.py"]


def test_watch_globs_stay_top_level(src_repo: Path) -> None:
    # The anti-narrowing invariant (§10): the map may descend, the net may not.
    # A `src/webfx/**` watch would stop watching anything else added under
    # `src/`, and an unwatched change reports a false `fresh`.
    scan = scanner.scan(src_repo)
    assert scan.source_dirs == ["src", "tests"]
    watches = context.default_watches(context.spec_by_name("modules"), scan)
    assert "src/**" in watches
    assert not any(w.startswith("src/webfx") for w in watches)


def test_a_new_package_under_src_is_still_watched(src_repo: Path) -> None:
    scan = scanner.scan(src_repo)
    watches = context.default_watches(context.spec_by_name("modules"), scan)
    from slate import globs
    assert globs.any_match(watches, "src/other/thing.py")


def test_edges_resolve_through_the_src_prefix(src_repo: Path) -> None:
    # `from webfx.json.provider import X` names no directory called `webfx`;
    # first-segment matching finds nothing and the graph comes back empty.
    edges = scanner.scan(src_repo).edges
    assert edges["tests"] == {"src/webfx/json"}


def test_relative_imports_produce_edges(src_repo: Path) -> None:
    edges = scanner.scan(src_repo).edges
    assert edges["src/webfx"] == {"src/webfx/json", "src/webfx/sansio"}
    assert edges["src/webfx/json"] == {"src/webfx"}


def test_stdlib_import_does_not_alias_a_nested_directory(src_repo: Path) -> None:
    # `src/webfx/json/provider.py` does `import json` (the stdlib). Indexing
    # nested dirs by basename would resolve that to the sibling package and
    # invent a self-edge that is not in the code.
    edges = scanner.scan(src_repo).edges
    assert "src/webfx/json" not in edges["src/webfx/json"]


def test_graph_is_deterministic_across_scans(src_repo: Path) -> None:
    first = scanner.scan(src_repo)
    second = scanner.scan(src_repo)
    assert first.edges == second.edges
    assert [m.name for m in first.modules] == [m.name for m in second.modules]


def test_flat_layout_is_unchanged(repo: Path) -> None:
    # The fixture repo (`demo/`, `tests/`) must map exactly as it did before.
    scan = scanner.scan(repo)
    assert scan.source_dirs == ["demo", "tests"]
    assert scan.module_paths == ["demo", "tests"]


def test_row_budget_prefers_source_over_supporting_trees(tmp_path: Path) -> None:
    root = tmp_path / "big"
    root.mkdir()
    git(root, "init", "-q")
    (root / "README.md").write_text("# big\n")
    pkg = root / "src" / "big"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("x = 1\n")
    # Twenty test directories, each large enough to earn a row on size alone.
    for i in range(20):
        d = root / "tests" / f"suite_{i:02d}"
        d.mkdir(parents=True)
        for j in range(4):
            (d / f"test_{j}.py").write_text("def test():\n    assert True\n")
    commit_all(root, "initial")

    names = [m.name for m in scanner.scan(root).modules]
    assert len(names) <= scanner._MAX_MODULE_ROWS
    assert "src/big" in names  # source survives the cap
