"""Shared fixture: a small throwaway git repo that looks like a real project."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

GIT_ENV_ARGS = [
    "-c", "user.email=test@slate.local",
    "-c", "user.name=Slate Tests",
    "-c", "commit.gpgsign=false",
]


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *GIT_ENV_ARGS, *args],
        capture_output=True, text=True, check=True,
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

    (root / "README.md").write_text("# Demo Project\n\nA fixture repo.\n")
    (root / "Makefile").write_text(
        ".PHONY: test build\n\ntest:\n\tpytest\n\nbuild:\n\techo build\n"
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n'
        "[project.scripts]\ndemo = \"demo.cli:main\"\n"
    )
    src = root / "demo"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "cli.py").write_text("def main():\n    return 0\n")
    (src / "engine.py").write_text("def run():\n    return 42\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_engine.py").write_text("def test_run():\n    assert True\n")

    commit_all(root, "initial")
    return root
