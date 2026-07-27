"""The git merge driver: human text survives, facts are left to sync.

The end-to-end tests drive real merges in real git repos — the driver's
whole reason to exist is a git behavior, so mocking it would test nothing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from slate import context, freshness, generator, gitutil, merge, scanner
from slate.cli import main
from slate.context import FRESH, STALE

from .conftest import GIT_ENV_ARGS, commit_all, git

ARCH = ".slate/architecture.md"


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def install_driver(repo: Path) -> None:
    """Install, then point the driver at this interpreter.

    `slate` may not be on PATH in a test environment; the command still goes
    through the real CLI entry point, so the driver path is genuinely covered.
    """
    merge.install(repo)
    git(repo, "config", merge.DRIVER_CONFIG,
        f'"{sys.executable}" -m slate.cli merge run %O %A %B %P')


def default_branch(repo: Path) -> str:
    """Whatever `git init` called it here — master or main, per git version."""
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def try_merge(repo: Path, branch: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *GIT_ENV_ARGS, "merge", branch, "-m", f"merge {branch}"],
        capture_output=True, text=True, env={**_env(), "PYTHONPATH": _pkg_parent()},
    )


def _env() -> dict:
    import os
    return dict(os.environ)


def _pkg_parent() -> str:
    return str(Path(__file__).resolve().parents[1])


def append_note(repo: Path, rel: str, note: str) -> None:
    path = repo / rel
    path.write_text(path.read_text().rstrip() + f"\n\n{note}\n")


# --- installation -----------------------------------------------------------

def test_install_registers_both_halves(repo: Path) -> None:
    merge.install(repo)
    assert merge.driver_registered(repo)
    assert merge.attributes_registered(repo)
    attrs = (repo / ".gitattributes").read_text()
    assert f"AGENTS.md merge={merge.DRIVER}" in attrs
    assert f"{ARCH} merge={merge.DRIVER}" in attrs
    assert gitutil.config_get(repo, merge.DRIVER_CONFIG) == merge.DRIVER_COMMAND


def test_install_is_idempotent(repo: Path) -> None:
    merge.install(repo)
    merge.install(repo)
    assert (repo / ".gitattributes").read_text().count(merge.ATTR_BEGIN) == 1


def test_install_preserves_foreign_attributes(repo: Path) -> None:
    (repo / ".gitattributes").write_text("*.png binary\n")
    merge.install(repo)
    text = (repo / ".gitattributes").read_text()
    assert "*.png binary" in text
    assert merge.ATTR_BEGIN in text


def test_uninstall_removes_both_halves(repo: Path) -> None:
    merge.install(repo)
    assert merge.uninstall(repo) is True
    assert not merge.driver_registered(repo)
    assert not (repo / ".gitattributes").exists()  # we created it; don't litter
    assert merge.uninstall(repo) is False


def test_uninstall_keeps_foreign_attributes(repo: Path) -> None:
    (repo / ".gitattributes").write_text("*.png binary\n")
    merge.install(repo)
    merge.uninstall(repo)
    assert (repo / ".gitattributes").read_text() == "*.png binary\n"


def test_cli_status_reports_missing_wiring(repo: Path, capsys) -> None:
    assert main(["-C", str(repo), "merge", "status"]) == 0
    assert "not registered" in capsys.readouterr().out
    assert main(["-C", str(repo), "merge", "install"]) == 0
    capsys.readouterr()
    assert main(["-C", str(repo), "merge", "status"]) == 0
    out = capsys.readouterr().out
    assert "registered" in out and "present" in out


# --- the block placeholder --------------------------------------------------

def test_placehold_restore_roundtrip() -> None:
    body = context.replace_auto_block("# Title\n\nhuman words\n", "| a | b |")
    held = merge._placehold(body)
    assert context.AUTO_BEGIN not in held
    assert merge.PLACEHOLDER in held
    assert merge._restore(held, "| a | b |") == body


def test_restore_appends_when_placeholder_lost() -> None:
    restored = merge._restore("# Title\n\nhuman words\n", "| a | b |")
    assert context.get_auto_block(restored) == "| a | b |"
    assert "human words" in restored


# --- merging one file -------------------------------------------------------

def write_doc(
    path: Path, intro: str, notes: str, block: str, watches: list[str]
) -> None:
    from slate import frontmatter
    meta = {"slate_doc": "architecture", "slate_synced_commit": "aaa1111",
            "slate_watches": watches}
    body = context.replace_auto_block(f"# Architecture\n\n{intro}\n", block)
    path.write_text(frontmatter.render(meta, f"{body}\n## Notes\n\n{notes}\n"))


def test_run_merges_cleanly_when_only_the_facts_differ(tmp_path: Path) -> None:
    """The dominant case: two branches both ran `slate sync`, nobody touched
    the prose. Today that conflicts in every generated doc; here it must not."""
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    write_doc(base, "intro.", "a note.", "| base |", ["src/**"])
    write_doc(ours, "intro.", "a note.", "| ours |", ["src/**"])
    write_doc(theirs, "intro.", "a note.", "| theirs |", ["src/**"])

    code, message = merge.run(base, ours, theirs, ARCH)

    assert code == 0
    from slate import frontmatter
    _, body = frontmatter.parse(ours.read_text())
    # Ours' block is kept verbatim — sync regenerates it from the merged tree.
    assert context.get_auto_block(body) == "| ours |"
    assert "sync" in message


def test_run_keeps_both_sides_edits_and_unions_watches(tmp_path: Path) -> None:
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    write_doc(base, "intro.", "a note.", "| base |", ["src/**"])
    write_doc(ours, "ALICE: billing runs first.", "a note.", "| ours |", ["src/**"])
    write_doc(theirs, "intro.", "a note.\n\nBOB: notify is fire-and-forget.",
              "| theirs |", ["src/**", "docs/**"])

    code, _ = merge.run(base, ours, theirs, ARCH)

    assert code == 0
    result = ours.read_text()
    assert "ALICE: billing runs first." in result
    assert "BOB: notify is fire-and-forget." in result
    from slate import frontmatter
    meta, _ = frontmatter.parse(result)
    assert meta["slate_watches"] == ["src/**", "docs/**"]


def test_run_conflicts_only_in_human_text(tmp_path: Path) -> None:
    """Two branches rewriting the same sentence is a real conflict — but the
    markers stay in the prose and the generated facts come through clean."""
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    write_doc(base, "the system is small.", "a note.", "| same |", ["src/**"])
    write_doc(ours, "the system is medium.", "a note.", "| same |", ["src/**"])
    write_doc(theirs, "the system is enormous.", "a note.", "| same |", ["src/**"])

    code, message = merge.run(base, ours, theirs, ARCH)

    assert code == 1
    result = ours.read_text()
    assert "<<<<<<< ours" in result and ">>>>>>> theirs" in result
    from slate import frontmatter
    _, body = frontmatter.parse(result)
    assert context.get_auto_block(body) == "| same |"
    assert "conflict" in message


def test_run_falls_back_for_non_context_files(tmp_path: Path) -> None:
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    base.write_text("one\n")
    ours.write_text("one\ntwo\n")
    theirs.write_text("zero\none\n")
    code, message = merge.run(base, ours, theirs, "src/app.py")
    assert code == 0
    assert ours.read_text() == "zero\none\ntwo\n"
    assert message == ""


def test_append_only_log_unions_both_entries(tmp_path: Path) -> None:
    """Two branches each appending a decision is not a conflict — the log is
    append-only, so both entries are kept (order is the reviewer's problem)."""
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    from slate import frontmatter
    meta = {"slate_doc": "decisions", "slate_synced_commit": "aaa1111"}
    base.write_text(frontmatter.render(dict(meta), "# Decisions\n"))
    ours.write_text(frontmatter.render(dict(meta), "# Decisions\n\n## 2026-01-01 alice\n"))
    theirs.write_text(frontmatter.render(dict(meta), "# Decisions\n\n## 2026-01-02 bob\n"))

    code, _ = merge.run(base, ours, theirs, ".slate/decisions.md")

    assert code == 0
    result = ours.read_text()
    assert "alice" in result and "bob" in result
    assert "<<<<<<<" not in result
    assert context.AUTO_BEGIN not in result


def test_non_append_only_human_doc_still_conflicts(tmp_path: Path) -> None:
    """read-next is rewritten, not appended — union would be wrong there."""
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    from slate import frontmatter
    meta = {"slate_doc": "read-next", "slate_synced_commit": "aaa1111"}
    base.write_text(frontmatter.render(dict(meta), "# Read next\n\nfocus: nothing.\n"))
    ours.write_text(frontmatter.render(dict(meta), "# Read next\n\nfocus: billing.\n"))
    theirs.write_text(frontmatter.render(dict(meta), "# Read next\n\nfocus: notify.\n"))

    code, _ = merge.run(base, ours, theirs, ".slate/read-next.md")

    assert code == 1
    assert "<<<<<<<" in ours.read_text()


# --- end to end, through git ------------------------------------------------

def branch_work(repo: Path, name: str, trunk: str, path: str, code: str,
                note: str | None = None) -> None:
    """A branch that changes code, optionally adds a note, and syncs."""
    git(repo, "checkout", "-q", trunk)
    git(repo, "checkout", "-qb", name)
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code)
    if note:
        append_note(repo, ARCH, note)
    commit_all(repo, f"{name} work")
    assert main(["-C", str(repo), "sync"]) == 0
    commit_all(repo, f"{name} sync")


def test_concurrent_syncs_merge_without_conflict(repo: Path) -> None:
    """The headline case: two branches synced, neither touched the prose.

    Without the driver this conflicts in all four generated docs, purely
    because each sync rewrote the anchor and the auto-block.
    """
    init_layer(repo)
    install_driver(repo)
    commit_all(repo, "install merge driver")
    trunk = default_branch(repo)

    branch_work(repo, "alice", trunk, "demo/billing.py", "def tax(x):\n    return x\n")
    branch_work(repo, "bob", trunk, "demo/notify.py", "def send(m):\n    return m\n")

    git(repo, "checkout", "-q", trunk)
    git(repo, "merge", "alice", "-m", "merge alice")
    result = try_merge(repo, "bob")

    assert result.returncode == 0, result.stdout + result.stderr
    for spec in (ARCH, "AGENTS.md", ".slate/modules.md", ".slate/workflows.md"):
        assert "<<<<<<<" not in (repo / spec).read_text(), spec


def test_concurrent_prose_appends_conflict_without_losing_either(repo: Path) -> None:
    """Both branches appending a note at the same point is a real conflict —
    git cannot know the intended order. What matters is that neither note is
    lost and the conflict is confined to the prose."""
    init_layer(repo)
    install_driver(repo)
    commit_all(repo, "install merge driver")
    trunk = default_branch(repo)

    branch_work(repo, "alice", trunk, "demo/billing.py",
                "def tax(x):\n    return x\n", "ALICE: billing runs before auth.")
    branch_work(repo, "bob", trunk, "demo/notify.py",
                "def send(m):\n    return m\n", "BOB: notify is fire-and-forget.")

    git(repo, "checkout", "-q", trunk)
    git(repo, "merge", "alice", "-m", "merge alice")
    result = try_merge(repo, "bob")

    assert result.returncode != 0
    text = (repo / ARCH).read_text()
    # Neither side's prose was dropped — the whole point.
    assert "ALICE: billing runs before auth." in text
    assert "BOB: notify is fire-and-forget." in text
    # The docs whose prose nobody touched still merged cleanly.
    for spec in ("AGENTS.md", ".slate/modules.md", ".slate/workflows.md"):
        assert "<<<<<<<" not in (repo / spec).read_text(), spec
    # The generated facts came through outside the conflict region.
    from slate import frontmatter
    _, body = frontmatter.parse(text)
    block = context.get_auto_block(body)
    assert block is not None and "<<<<<<<" not in block


def test_merged_layer_is_not_falsely_fresh(repo: Path) -> None:
    """The safety property: a driver merge can never manufacture `fresh`.

    Ours' frontmatter anchor and auto-block are kept verbatim, so the merged
    doc describes only alice's tree. Freshness must still notice bob's module.
    """
    init_layer(repo)
    install_driver(repo)
    commit_all(repo, "install merge driver")
    trunk = default_branch(repo)

    branch_work(repo, "alice", trunk, "demo/billing.py", "def tax(x):\n    return x\n")
    # Bob's file lands in the same watched tree, so the merged module map has
    # a file count neither side's auto-block states.
    branch_work(repo, "bob", trunk, "demo/notify.py", "def send(m):\n    return m\n")

    git(repo, "checkout", "-q", trunk)
    git(repo, "merge", "alice", "-m", "merge alice")
    result = try_merge(repo, "bob")
    assert result.returncode == 0, result.stdout + result.stderr

    modules = {r.doc.spec.name: r for r in freshness.evaluate_all(repo)}["modules"]
    assert modules.status == STALE, modules.reason
    assert main(["-C", str(repo), "sync"]) == 0
    assert {r.doc.spec.name: r for r in freshness.evaluate_all(repo)}["modules"].status == FRESH
