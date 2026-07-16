"""`slate hook` — a local freshness gate before code leaves the machine.

This installs a **pre-push** hook, deliberately not pre-commit: the sync
workflow is two commits (commit the code, then `slate sync` anchors the
docs to that commit and the doc update is committed on top). A pre-commit
`status --ci` would fail exactly when committing the code — blocking the
legitimate workflow. At push time the branch tip must be synced, which is
the same contract CI enforces (decision log 2026-07-15).
"""

from __future__ import annotations

from pathlib import Path

from . import gitutil

HOOK_NAME = "pre-push"
MARKER = "installed by `slate hook install`"

_HOOK_BODY = f"""#!/bin/sh
# {MARKER} — `slate hook uninstall` removes it
exec slate -C "$(git rev-parse --show-toplevel)" status --ci
"""


class HookError(RuntimeError):
    pass


def hook_path(root: Path) -> Path:
    return gitutil.hooks_dir(root) / HOOK_NAME


def is_ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text()
    except (OSError, UnicodeDecodeError):
        return False


def install(root: Path, force: bool = False) -> Path:
    path = hook_path(root)
    if path.exists() and not is_ours(path) and not force:
        raise HookError(
            f"{path} already exists and was not installed by slate — "
            "--force overwrites it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HOOK_BODY)
    path.chmod(0o755)
    return path


def uninstall(root: Path) -> bool:
    """Remove the hook. Returns False if none of ours was present."""
    path = hook_path(root)
    if not path.exists():
        return False
    if not is_ours(path):
        raise HookError(f"{path} was not installed by slate — not touching it")
    path.unlink()
    return True
