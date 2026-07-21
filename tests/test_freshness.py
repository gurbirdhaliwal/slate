from pathlib import Path

from slate import context, freshness, generator, scanner
from slate.context import FRESH, NEEDS_VERIFICATION, STALE

from .conftest import commit_all, git


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def report_for(repo: Path, name: str) -> freshness.DocReport:
    reports = {r.doc.spec.name: r for r in freshness.evaluate_all(repo)}
    return reports[name]


def test_everything_fresh_after_init(repo: Path) -> None:
    init_layer(repo)
    for r in freshness.evaluate_all(repo):
        assert r.status == FRESH, (r.rel_path, r.reason)


def test_content_edit_that_keeps_facts_stays_fresh(repo: Path) -> None:
    # Editing a function body doesn't move a module: the regenerated
    # auto-block is identical, so the doc provably still checks out.
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    r = report_for(repo, "modules")
    assert r.status == FRESH
    assert r.content_verified
    assert r.changed_watched == ["demo/engine.py"]  # evidence still reported


def test_uncommitted_new_file_marks_stale(repo: Path) -> None:
    # A new file changes the module map's file counts — genuinely stale.
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert r.changed_watched == ["demo/widget.py"]


def test_human_claim_about_changed_path_marks_stale(repo: Path) -> None:
    # The scan can't vouch for hand-written claims: if a human section
    # references the changed path, content verification must not apply.
    init_layer(repo)
    path = repo / ".slate" / "modules.md"
    path.write_text(path.read_text() + "\n`demo/engine.py` is the hot path.\n")
    commit_all(repo, "note the hot path")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    r = report_for(repo, "modules")
    assert r.status == STALE


def test_committed_watched_change_marks_stale(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "new_module.py").write_text("x = 1\n")
    commit_all(repo, "add module")
    assert report_for(repo, "modules").status == STALE
    assert report_for(repo, "architecture").status == STALE


def test_unwatched_change_stays_fresh(repo: Path) -> None:
    init_layer(repo)
    (repo / "README.md").write_text("# Demo Project\n\nUpdated prose.\n")
    commit_all(repo, "readme only")
    assert report_for(repo, "modules").status == FRESH
    assert report_for(repo, "workflows").status == FRESH


def test_editing_the_doc_itself_does_not_mark_it_stale(repo: Path) -> None:
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + "\n- working on the parser\n")
    assert report_for(repo, "read-next").status == FRESH


def test_sync_clears_staleness(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "new_module.py").write_text("x = 1\n")
    commit_all(repo, "add module")
    assert report_for(repo, "modules").status == STALE

    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("modules"))
    generator.sync_doc(doc, scan)
    commit_all(repo, "sync context")
    assert report_for(repo, "modules").status == FRESH
    # And the regenerated module map actually mentions the new file's module.
    assert "demo/" in context.spec_by_name("modules").path(repo).read_text()


def setup_symbol_claim(repo: Path) -> None:
    """Give engine.py two functions and have modules.md claim one by symbol.

    The module map's auto-block is identical for any body edit to engine.py
    (counts, language, and entry hints don't move), so the *only* thing that
    can flip modules.md fresh↔stale is the symbol-level claim.
    """
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 42\n\n\ndef helper():\n    return 1\n"
    )
    commit_all(repo, "engine with two functions")
    init_layer(repo)
    path = repo / ".slate" / "modules.md"
    path.write_text(path.read_text() + "\nThe `engine.run` entry point drives the loop.\n")
    commit_all(repo, "claim engine.run by symbol")


def test_change_to_referenced_symbol_marks_stale(repo: Path) -> None:
    # modules.md claims `engine.run`; run's body changed → the claim is in
    # question. Before symbol resolution this was a false *fresh* (the path was
    # never backticked and the auto-block regenerates identically).
    setup_symbol_claim(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 99\n\n\ndef helper():\n    return 1\n"
    )
    r = report_for(repo, "modules")
    assert r.status == STALE


def test_change_to_unreferenced_symbol_stays_fresh(repo: Path) -> None:
    # `helper` changed but the doc only claims `engine.run` — provably
    # untouched, so the doc stays fresh (the headline precision win).
    setup_symbol_claim(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 42\n\n\ndef helper():\n    return 2\n"
    )
    r = report_for(repo, "modules")
    assert r.status == FRESH
    assert r.content_verified
    assert "demo/engine.py" in r.changed_watched  # evidence still attached


def test_docstring_only_edit_to_referenced_file_stays_fresh(repo: Path) -> None:
    # A module-docstring typo in the referenced file touches no symbol — the
    # old path-level rule would have flagged this file stale (false positive).
    setup_symbol_claim(repo)
    (repo / "demo" / "engine.py").write_text(
        '"""Engine internals."""\n\n\ndef run():\n    return 42\n\n\ndef helper():\n    return 1\n'
    )
    r = report_for(repo, "modules")
    assert r.status == FRESH
    assert r.content_verified


def test_unparseable_referenced_file_falls_back_to_stale(repo: Path) -> None:
    # A syntax error makes engine.py opaque; the referenced symbol can't be
    # proven untouched, so the conservative fallback keeps the doc stale.
    setup_symbol_claim(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run(:\n    return 42\n\n\ndef helper():\n    return 1\n"
    )
    r = report_for(repo, "modules")
    assert r.status == STALE


def orphan_anchor(repo: Path, doc: str) -> Path:
    """Point a doc's sync anchor at a commit that doesn't exist (squash/rebase)."""
    path = repo / ".slate" / f"{doc}.md" if doc != "agents" else repo / "AGENTS.md"
    text = path.read_text().replace("slate_synced_commit: ", "slate_synced_commit: deadbee")
    path.write_text(text)
    return path


def test_orphaned_anchor_recovers_via_digest(repo: Path) -> None:
    # Squash-merge kills commit anchors; the content digest must prove the
    # watched files are unchanged so the layer doesn't degrade to a rumor.
    init_layer(repo)
    orphan_anchor(repo, "modules")
    r = report_for(repo, "modules")
    assert r.status == FRESH
    assert r.content_verified
    assert "rewritten" in r.reason


def test_orphaned_anchor_with_changed_content_is_stale(repo: Path) -> None:
    init_layer(repo)
    orphan_anchor(repo, "modules")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert "demo/engine.py" in r.changed_watched  # working-tree evidence


def test_orphaned_anchor_with_committed_change_is_stale(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    commit_all(repo, "add widget")
    orphan_anchor(repo, "modules")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert "rewritten" in r.reason


def test_orphaned_anchor_without_digest_needs_verification(repo: Path) -> None:
    # Pre-digest layers (or hand-stripped metadata) stay unknowable.
    init_layer(repo)
    path = orphan_anchor(repo, "modules")
    lines = [
        line for line in path.read_text().splitlines()
        if not line.startswith("slate_synced_digest")
    ]
    path.write_text("\n".join(lines) + "\n")
    r = report_for(repo, "modules")
    assert r.status == NEEDS_VERIFICATION
    assert "deadbee" in r.reason


def test_orphaned_anchor_on_human_doc_recovers(repo: Path) -> None:
    # Human-owned docs have no watches, so nothing watchable can have
    # changed — an orphaned anchor must not turn the attestation into a rumor.
    init_layer(repo)
    orphan_anchor(repo, "read-next")
    assert report_for(repo, "read-next").status == FRESH


def test_digest_ignores_context_doc_edits(repo: Path) -> None:
    # AGENTS.md watches .slate/**, but docs never invalidate docs — editing
    # the layer must not break digest recovery after a history rewrite.
    init_layer(repo)
    orphan_anchor(repo, "agents")
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + "\n- working on the parser\n")
    assert report_for(repo, "agents").status == FRESH


def test_no_anchor_needs_verification(repo: Path) -> None:
    init_layer(repo)
    path = repo / ".slate" / "decisions.md"
    lines = [
        line for line in path.read_text().splitlines()
        if not line.startswith("slate_synced_commit")
    ]
    path.write_text("\n".join(lines) + "\n")
    assert report_for(repo, "decisions").status == NEEDS_VERIFICATION


def test_rename_that_changes_facts_counts_as_change(repo: Path) -> None:
    # main.py is an entry hint, so this rename alters the module map's claims.
    init_layer(repo)
    git(repo, "mv", "demo/engine.py", "demo/main.py")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert "demo/main.py" in r.changed_watched


def test_rename_that_keeps_facts_is_content_verified(repo: Path) -> None:
    # Neither name is an entry hint: counts, language, and hints are all
    # unchanged, so the doc provably still checks out — rename detection
    # still supplies the evidence.
    init_layer(repo)
    git(repo, "mv", "demo/engine.py", "demo/core.py")
    r = report_for(repo, "modules")
    assert r.status == FRESH
    assert r.content_verified
    assert "demo/core.py" in r.changed_watched


def test_untracked_directory_files_reported_individually(repo: Path) -> None:
    # git status collapses untracked dirs to "newdir/" without -uall; watch
    # globs need real file paths, and context docs in a new .slate/ dir must
    # still be excludable from change detection.
    init_layer(repo)
    new_dir = repo / "demo" / "sub"
    new_dir.mkdir()
    (new_dir / "widget.py").write_text("x = 1\n")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert r.changed_watched == ["demo/sub/widget.py"]
