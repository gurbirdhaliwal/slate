"""Shared fixture: a small throwaway git repo that looks like a real project."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

GIT_ENV_ARGS = [
    "-c", "user.email=test@slate.local",
    "-c", "user.name=Slate Tests",
    "-c", "commit.gpgsign=false",
    # Housekeeping off. The co-change fixtures build ~130 commits in a couple
    # of seconds, which is enough loose objects to trip auto-gc; git may then
    # detach it, and a background repack holding the lock fails the *next*
    # commit with exit 128. Nothing here is a long-lived repo, so there is
    # nothing to maintain.
    "-c", "gc.auto=0",
    "-c", "gc.autoDetach=false",
    "-c", "maintenance.auto=false",
]


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *GIT_ENV_ARGS, *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # `check=True` raises with the command but not the reason, which cost
        # a CI round-trip: the failure read "exit status 128" and nothing else.
        raise AssertionError(
            f"git {' '.join(args)} failed ({proc.returncode})\n"
            f"stdout: {proc.stdout.strip()}\nstderr: {proc.stderr.strip()}"
        )
    return proc.stdout


def commit_all(root: Path, message: str = "change") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "--short", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    root.mkdir()
    git(root, "init", "-q")

    (root / "README.md").write_text("# Demo Project\n\nA fixture repo.\n", encoding="utf-8")
    (root / "Makefile").write_text(
        ".PHONY: test build\n\ntest:\n\tpytest\n\nbuild:\n\techo build\n"
    , encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n'
        "[project.scripts]\ndemo = \"demo.cli:main\"\n"
    , encoding="utf-8")
    src = root / "demo"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (src / "engine.py").write_text("def run():\n    return 42\n", encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_engine.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")

    commit_all(root, "initial")
    return root
