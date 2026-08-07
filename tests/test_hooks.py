import os
from pathlib import Path

import pytest

from slate import hooks
from slate.cli import main


def test_install_creates_executable_hook(repo: Path) -> None:
    path = hooks.install(repo)
    assert path.name == "pre-push"
    assert hooks.MARKER in path.read_text(encoding="utf-8")
    assert os.access(path, os.X_OK)
    assert "status --ci" in path.read_text(encoding="utf-8")


def test_install_is_idempotent(repo: Path) -> None:
    hooks.install(repo)
    hooks.install(repo)  # ours already there — overwriting ours is fine


def test_refuses_foreign_hook_without_force(repo: Path) -> None:
    path = hooks.hook_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho custom hook\n", encoding="utf-8")
    with pytest.raises(hooks.HookError):
        hooks.install(repo)
    hooks.install(repo, force=True)
    assert hooks.MARKER in path.read_text(encoding="utf-8")


def test_uninstall(repo: Path) -> None:
    hooks.install(repo)
    assert hooks.uninstall(repo) is True
    assert not hooks.hook_path(repo).exists()
    assert hooks.uninstall(repo) is False


def test_uninstall_refuses_foreign_hook(repo: Path) -> None:
    path = hooks.hook_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho custom hook\n", encoding="utf-8")
    with pytest.raises(hooks.HookError):
        hooks.uninstall(repo)


def test_cli_hook_roundtrip(repo: Path, capsys) -> None:
    assert main(["-C", str(repo), "hook", "install"]) == 0
    assert "pre-push" in capsys.readouterr().out
    assert main(["-C", str(repo), "hook", "uninstall"]) == 0


def test_cli_hook_foreign_exits_2(repo: Path, capsys) -> None:
    path = hooks.hook_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
    assert main(["-C", str(repo), "hook", "install"]) == 2
