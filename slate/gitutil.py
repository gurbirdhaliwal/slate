"""Thin wrappers over the git CLI.

Slate's change detection is anchored to git: every context doc records the
commit it was last synced at, and staleness is "what changed since then",
including uncommitted working-tree edits. All functions take the repo root
explicitly — nothing here depends on process CWD.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def is_git_repo(root: Path) -> bool:
    try:
        return _git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except (GitError, FileNotFoundError):
        return False


def head_commit(root: Path) -> str | None:
    """Short SHA of HEAD, or None on an unborn branch (no commits yet)."""
    try:
        return _git(root, "rev-parse", "--short", "HEAD").strip()
    except GitError:
        return None


def commit_exists(root: Path, sha: str) -> bool:
    try:
        _git(root, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def list_files(root: Path) -> list[str]:
    """Files in the *working tree*: tracked + untracked-but-not-ignored.

    ls-files reports the index, which still contains files deleted on disk
    but not yet staged — the scan must describe what actually exists, so
    those are filtered out.
    """
    out = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    return [line for line in out.splitlines() if line and (root / line).exists()]


def changed_files(root: Path, since: str | None) -> list[str]:
    """Paths changed since a commit, plus any uncommitted working-tree changes.

    If ``since`` is None or no longer resolvable, only working-tree changes
    are returned — callers treat an unresolvable anchor as needs-verification
    rather than guessing at history.
    """
    changed: set[str] = set()
    if since and commit_exists(root, since):
        out = _git(root, "diff", "--name-only", "-M", since, "HEAD")
        changed.update(line for line in out.splitlines() if line)
    # Working tree: staged, unstaged, and untracked (not ignored). -uall lists
    # files inside untracked directories individually — without it git reports
    # a collapsed "newdir/", which watch globs and doc-path filters can't use.
    out = _git(root, "status", "--porcelain", "-uall")
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:  # rename: count both sides as changed
            old, new = path.split(" -> ", 1)
            changed.add(_unquote(old))
            changed.add(_unquote(new))
        else:
            changed.add(_unquote(path))
    return sorted(changed)


def changed_with_status(root: Path, since: str | None) -> dict[str, str]:
    """Like changed_files, but with a change kind per path: A/M/D/R.

    Working-tree state wins over committed state for the same path (the AI
    acts on the working tree). Renames report the *new* path as R.
    """
    kinds: dict[str, str] = {}
    if since and commit_exists(root, since):
        out = _git(root, "diff", "--name-status", "-M", since, "HEAD")
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].startswith("R"):
                kinds[_unquote(parts[1])] = "D"
                kinds[_unquote(parts[2])] = "R"
            elif len(parts) == 2:
                kinds[_unquote(parts[1])] = parts[0][:1]
    out = _git(root, "status", "--porcelain", "-uall")
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:
            old, new = path.split(" -> ", 1)
            kinds[_unquote(old)] = "D"
            kinds[_unquote(new)] = "R"
        elif code == "??":
            kinds[_unquote(path)] = "A"
        elif "D" in code:
            kinds[_unquote(path)] = "D"
        else:
            kinds[_unquote(path)] = "M"
    return kinds


def hooks_dir(root: Path) -> Path:
    """The active hooks directory (worktree- and core.hooksPath-aware)."""
    out = _git(root, "rev-parse", "--git-path", "hooks").strip()
    path = Path(out)
    return path if path.is_absolute() else root / path


def commits_since(root: Path, since: str) -> int:
    try:
        return int(_git(root, "rev-list", "--count", f"{since}..HEAD").strip())
    except (GitError, ValueError):
        return 0


def _unquote(path: str) -> str:
    # git quotes paths with special characters: "a b.txt"
    if path.startswith('"') and path.endswith('"'):
        return path[1:-1]
    return path


def fleet_roots(paths: list[Path]) -> list[Path]:
    """Each arg is a repo, or a parent whose immediate children are checked."""
    roots: list[Path] = []
    for path in paths:
        path = path.resolve()
        if (path / ".git").exists():
            roots.append(path)
            continue
        if path.is_dir():
            roots.extend(sorted(
                child for child in path.iterdir()
                if child.is_dir() and (child / ".git").exists()
            ))
    return roots
