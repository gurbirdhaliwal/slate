"""Thin wrappers over the git CLI.

Slate's change detection is anchored to git: every context doc records the
commit it was last synced at, and staleness is "what changed since then",
including uncommitted working-tree edits. All functions take the repo root
explicitly — nothing here depends on process CWD.
"""

from __future__ import annotations

import re
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


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_hunks(root: Path, since: str | None) -> dict[str, list[tuple[int, int]]]:
    """Per-file changed line ranges (new-side) between ``since`` and the worktree.

    ``git diff --unified=0 <since>`` diffs the commit against the working tree
    (committed *and* uncommitted edits), so the ranges are line numbers in the
    file currently on disk — exactly what ``symbols.changed_symbols`` parses.
    Untracked files never appear in that diff, so each is reported whole; a new
    file is entirely changed.

    A pure deletion hunk (``+c,0``) records the gap around line ``c`` so the
    enclosing definition still counts as touched. When ``since`` is missing or
    unresolvable only untracked files can be reported — the caller treats an
    unknowable history conservatively rather than guessing.
    """
    hunks: dict[str, list[tuple[int, int]]] = {}
    if since and commit_exists(root, since):
        out = _git(root, "diff", "--unified=0", "-M", "--no-color", since, "--")
        _parse_hunks(out, hunks)
    others = _git(root, "ls-files", "--others", "--exclude-standard")
    for rel in others.splitlines():
        if not rel or not (root / rel).exists():
            continue
        try:
            line_count = (root / rel).read_text(errors="ignore").count("\n") + 1
        except OSError:
            line_count = 1
        hunks.setdefault(rel, []).append((1, max(line_count, 1)))
    return hunks


def _parse_hunks(diff: str, hunks: dict[str, list[tuple[int, int]]]) -> None:
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else _strip_diff_prefix(target)
            continue
        if current is None:
            continue
        match = _HUNK_HEADER.match(line)
        if not match:
            continue
        start = int(match.group(1))
        length = int(match.group(2)) if match.group(2) is not None else 1
        if length == 0:  # pure deletion: mark the gap around the anchor line
            anchor = max(start, 1)
            hunks.setdefault(current, []).append((anchor, anchor + 1))
        else:
            hunks.setdefault(current, []).append((start, start + length - 1))


def _strip_diff_prefix(target: str) -> str:
    # `+++ b/path`, or `+++ "b/quoted path"` when git quotes special chars.
    target = _unquote(target)
    return target[2:] if target.startswith("b/") else target


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


def config_get(root: Path, key: str) -> str | None:
    try:
        return _git(root, "config", "--get", key).strip()
    except GitError:
        return None


def config_set(root: Path, key: str, value: str) -> None:
    _git(root, "config", key, value)


def config_unset(root: Path, key: str) -> bool:
    """Unset a key. Returns False when it wasn't set."""
    try:
        _git(root, "config", "--unset", key)
        return True
    except GitError:
        return False


def merge_file(current: Path, base: Path, other: Path, union: bool = False) -> int:
    """3-way merge ``other`` into ``current`` in place; returns conflict count.

    Wraps ``git merge-file``, which needs no repository — the merge driver
    is handed three temp files and a path, not a worktree. git reports the
    number of conflicts as the exit status and -1 (255) for a real failure.

    ``union`` resolves overlaps by keeping both sides' lines instead of
    emitting markers — correct only for content that is appended and never
    rewritten (see ``DocSpec.append_only``).
    """
    proc = subprocess.run(
        [
            "git", "merge-file",
            *(["--union"] if union else []),
            "-L", "ours", "-L", "base", "-L", "theirs",
            str(current), str(base), str(other),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode > 127 or proc.returncode < 0:
        raise GitError(proc.stderr.strip() or "git merge-file failed")
    return proc.returncode


def hooks_dir(root: Path) -> Path:
    """The active hooks directory (worktree- and core.hooksPath-aware)."""
    out = _git(root, "rev-parse", "--git-path", "hooks").strip()
    path = Path(out)
    return path if path.is_absolute() else root / path


def state_dir(root: Path) -> Path:
    """Slate's clone-local state directory inside the git dir (worktree-aware).

    State here (e.g. the value ledger) is per-clone by design: never tracked,
    never in the diff, and invisible to the freshness engine.
    """
    out = _git(root, "rev-parse", "--git-path", "slate").strip()
    path = Path(out)
    return path if path.is_absolute() else root / path


def commits_since(root: Path, since: str) -> int:
    try:
        return int(_git(root, "rev-list", "--count", f"{since}..HEAD").strip())
    except (GitError, ValueError):
        return 0


# git blames working-tree lines to the all-zero SHA; callers read it as
# "newer than any commit", which is what an uncommitted edit is.
UNCOMMITTED = "0" * 40


def last_change_commit(root: Path, path: str, since: str) -> str | None:
    """Full SHA of the newest commit in ``(since, HEAD]`` that touched `path`.

    None when nothing in that range touched it, or when git cannot say.
    """
    try:
        out = _git(root, "log", "-1", "--format=%H", f"{since}..HEAD", "--", path)
    except GitError:
        return None
    return out.strip() or None


def file_at_commit(root: Path, path: str, commit: str) -> str | None:
    """A tracked file's contents at `commit`, or None if it wasn't there.

    None is the answer for "added since", "deleted", and "not a git repo"
    alike; every caller here treats an unanswerable question as no evidence
    rather than guessing, so they do not need to be told apart.
    """
    if not _is_sha(commit) and not commit:
        return None
    try:
        return _git(root, "show", f"{commit}:{path}")
    except Exception:
        return None


def blame_lines(root: Path, path: str) -> dict[int, str] | None:
    """Map every 1-based line of `path` to the commit that last wrote it.

    Blames the whole file in one call — callers ask about many different line
    ranges in the same document, and per-range blame costs a git process each.
    Returns None when blame cannot answer (no file, no history) so callers can
    decline to act rather than guess.
    """
    try:
        out = _git(root, "blame", "--porcelain", "--", path)
    except GitError:
        return None
    blamed: dict[int, str] = {}
    for line in out.splitlines():
        head = line.split(" ")
        if len(head) >= 3 and len(head[0]) == 40 and _is_sha(head[0]):
            try:
                blamed[int(head[2])] = head[0]
            except ValueError:
                continue
    return blamed or None


def _is_sha(token: str) -> bool:
    return all(c in "0123456789abcdef" for c in token)


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """True when `ancestor` *is* `descendant` or one of its ancestors.

    Any error answers False, so an unresolvable pair never licenses a caller
    to treat one commit as reaching the other.
    """
    try:
        _git(root, "merge-base", "--is-ancestor", ancestor, descendant)
        return True
    except GitError:
        return False


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
