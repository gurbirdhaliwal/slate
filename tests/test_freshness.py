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


def test_uncommitted_watched_change_marks_stale(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert r.changed_watched == ["demo/engine.py"]


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


def test_missing_anchor_needs_verification(repo: Path) -> None:
    init_layer(repo)
    path = repo / ".slate" / "modules.md"
    text = path.read_text().replace("slate_synced_commit: ", "slate_synced_commit: deadbee")
    path.write_text(text)
    r = report_for(repo, "modules")
    assert r.status == NEEDS_VERIFICATION
    assert "deadbee" in r.reason


def test_no_anchor_needs_verification(repo: Path) -> None:
    init_layer(repo)
    path = repo / ".slate" / "decisions.md"
    lines = [
        line for line in path.read_text().splitlines()
        if not line.startswith("slate_synced_commit")
    ]
    path.write_text("\n".join(lines) + "\n")
    assert report_for(repo, "decisions").status == NEEDS_VERIFICATION


def test_rename_counts_as_change(repo: Path) -> None:
    init_layer(repo)
    git(repo, "mv", "demo/engine.py", "demo/core.py")
    r = report_for(repo, "modules")
    assert r.status == STALE
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
