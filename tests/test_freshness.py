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


def setup_two_symbol_claims(repo: Path) -> None:
    """engine.py has two functions; modules.md claims each by symbol.

    Editing one function's body must stale exactly its claim and leave the
    other fresh — the whole point of claim-level attribution.
    """
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 42\n\n\ndef helper():\n    return 1\n"
    )
    commit_all(repo, "engine with two functions")
    init_layer(repo)
    path = repo / ".slate" / "modules.md"
    path.write_text(
        path.read_text()
        + "\n## Claims\n\n"
        + "- The `engine.run` function drives the loop.\n"
        + "- The `engine.helper` function is a pure helper.\n"
    )
    commit_all(repo, "two symbol claims")


def human_claims(report: freshness.DocReport) -> list[freshness.ClaimVerdict]:
    return [c for c in report.claims if c.kind == "human"]


def test_only_the_referencing_claim_goes_stale(repo: Path) -> None:
    setup_two_symbol_claims(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 99\n\n\ndef helper():\n    return 1\n"
    )
    r = report_for(repo, "modules")
    hc = human_claims(r)
    stale = [c for c in hc if c.status == STALE]
    fresh = [c for c in hc if c.status == FRESH]
    assert len(stale) == 1 and "engine.run" in stale[0].refs
    assert any("engine.helper" in c.refs for c in fresh)


def test_one_suspect_claim_keeps_doc_out_of_fresh(repo: Path) -> None:
    # Roll-up invariant: a single non-fresh claim blocks doc-level fresh.
    setup_two_symbol_claims(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 99\n\n\ndef helper():\n    return 1\n"
    )
    r = report_for(repo, "modules")
    assert r.status == STALE
    assert len(r.suspect_claims) == 1


def test_all_claims_fresh_rolls_up_to_fresh(repo: Path) -> None:
    setup_two_symbol_claims(repo)
    # Touch neither referenced symbol: add an unrelated top-level name.
    (repo / "demo" / "engine.py").write_text(
        "def run():\n    return 42\n\n\ndef helper():\n    return 1\n\n\nUNUSED = 0\n"
    )
    r = report_for(repo, "modules")
    # engine.py changed but no claim's symbol moved → every claim fresh → fresh.
    assert r.status == FRESH
    assert r.content_verified
    assert all(c.status == FRESH for c in r.claims)


def test_unknowable_claim_blocks_fresh(repo: Path) -> None:
    # An unparseable referenced file can't prove the symbol untouched: the
    # claim is `unknowable`, and unknowable keeps the doc out of fresh (§10).
    setup_two_symbol_claims(repo)
    (repo / "demo" / "engine.py").write_text(
        "def run(:\n    return 42\n\n\ndef helper():\n    return 1\n"
    )
    r = report_for(repo, "modules")
    assert r.status == STALE
    unknowable = [c for c in human_claims(r) if c.status == freshness.CLAIM_UNKNOWABLE]
    assert unknowable, "expected an unknowable claim for the unparseable file"


def test_generated_fact_change_is_a_stale_claim(repo: Path) -> None:
    # Adding a file moves the module map: the specific generated line is a
    # stale claim, attributed at the line level.
    setup_two_symbol_claims(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    r = report_for(repo, "modules")
    assert r.status == STALE
    gen_stale = [c for c in r.claims if c.kind == "generated" and c.status == STALE]
    assert gen_stale
    # The two human symbol claims are untouched by adding an unrelated file.
    assert all(c.status == FRESH for c in human_claims(r))


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


# --- authorship narrowing: prose written against a change isn't rot ---------


def _claim(repo: Path, text: str) -> None:
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + f"\n{text}\n")


def test_prose_landing_with_the_code_is_not_stale(repo: Path) -> None:
    # The dominant false positive before this narrowing: a sentence written in
    # the same commit as the file it describes, flagged only because the doc's
    # anchor predates that commit.
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    _claim(repo, "The engine lives in `demo/engine.py` and returns 43.")
    commit_all(repo, "change engine and say so in the same commit")
    r = report_for(repo, "read-next")
    assert r.status == FRESH, r.reason


def test_prose_older_than_the_code_change_stays_stale(repo: Path) -> None:
    # The narrowing must not fire when the code moved *after* the prose.
    init_layer(repo)
    _claim(repo, "The engine lives in `demo/engine.py` and returns 42.")
    commit_all(repo, "describe the engine")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change the engine, leaving the prose behind")
    r = report_for(repo, "read-next")
    assert r.status == STALE, r.reason
    suspect = [c for c in r.suspect_claims if c.kind == "human"]
    assert any("demo/engine.py" in c.risk for c in suspect)


def test_uncommitted_prose_supersedes_committed_code(repo: Path) -> None:
    # Working-tree prose is newer than any commit; blame reports the all-zero
    # SHA and the claim must narrow to fresh rather than fail closed.
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change the engine")
    _claim(repo, "The engine lives in `demo/engine.py` and returns 43.")
    r = report_for(repo, "read-next")
    assert r.status == FRESH, r.reason


def test_narrowing_declines_when_blame_cannot_answer(repo: Path) -> None:
    # Every unanswerable question must leave the verdict alone. A false
    # `fresh` is the one failure the engine may never produce.
    init_layer(repo)
    _claim(repo, "The engine lives in `demo/engine.py` and returns 42.")
    commit_all(repo, "describe the engine")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change the engine")

    doc = context.load(repo, context.spec_by_name("read-next"))
    assert not freshness._prose_supersedes(repo, doc, [], ["demo/engine.py"], "HEAD~2")
    assert not freshness._prose_supersedes(repo, doc, [1], [], "HEAD~2")
    assert not freshness._prose_supersedes(
        repo, doc, [1], ["demo/engine.py"], "nonexistent-anchor"
    )


def test_symbol_prose_landing_with_the_code_is_not_stale(repo: Path) -> None:
    # The same narrowing reached through symbol resolution rather than a path
    # ref: `engine.run` moved, but the sentence describing it moved with it.
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    _claim(repo, "`engine.run` now returns 43.")
    commit_all(repo, "change run and describe it in the same commit")
    r = report_for(repo, "read-next")
    assert r.status == FRESH, r.reason


def test_symbol_prose_older_than_the_code_stays_stale(repo: Path) -> None:
    init_layer(repo)
    _claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run, leaving the prose behind")
    r = report_for(repo, "read-next")
    assert r.status == STALE, r.reason
    assert any("engine.run" in c.risk for c in r.suspect_claims if c.kind == "human")


def test_unresolvable_symbol_needs_prose_newer_than_every_change(repo: Path) -> None:
    # An unnameable qualifier widens the candidate set to every changed code
    # file (`_symbol_files`), so old prose cannot be narrowed by one unrelated
    # edit that happens to post-date it.
    init_layer(repo)
    _claim(repo, "`Mystery.method` is the entry point.")
    commit_all(repo, "describe something unresolvable")
    (repo / "demo" / "engine.py").write_text("def method():\n    return 1\n")
    commit_all(repo, "move a same-named symbol elsewhere")
    r = report_for(repo, "read-next")
    assert r.status == STALE, r.reason


# --- symbol refs resolve by module path, not by filename stem ---------------


def test_package_symbol_with_a_same_named_decoy_is_not_falsely_fresh(repo: Path) -> None:
    """The worst bug this engine can have, found on Flask's real layout.

    `pkg.request` lives in `pkg/__init__.py`, whose *stem* is `__init__`, so
    stem matching never saw it. Worse, an unrelated `fixtures/pkg.py` made the
    qualifier count as "known", which suppressed the conservative fallback —
    and the claim came back fresh while the code it described had moved.
    """
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("def request():\n    return 1\n")
    (repo / "fixtures").mkdir()
    (repo / "fixtures" / "pkg.py").write_text("DECOY = 1\n")
    commit_all(repo, "a package, and a decoy sharing its name")
    init_layer(repo)
    _claim(repo, "The `pkg.request` helper returns 1.")
    commit_all(repo, "describe it")

    (repo / "pkg" / "__init__.py").write_text("def request():\n    return 999\n")
    commit_all(repo, "move pkg.request")
    r = report_for(repo, "read-next")
    assert r.status == STALE, r.reason
    assert any("pkg.request" in c.risk for c in r.suspect_claims if c.kind == "human")


def test_dotted_ref_resolves_through_a_src_layout(repo: Path) -> None:
    # `app.views.View` names the module `app.views`, which lives at
    # src/app/views.py — the near-universal packaging layout.
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "views.py").write_text("class View:\n    pass\n")
    commit_all(repo, "add a src layout")
    init_layer(repo)
    _claim(repo, "See `app.views.View` for the base class.")
    commit_all(repo, "describe it")

    (repo / "src" / "app" / "views.py").write_text("class View:\n    x = 1\n")
    commit_all(repo, "move View")
    assert report_for(repo, "read-next").status == STALE


def test_module_resolution_does_not_flag_unrelated_changes(repo: Path) -> None:
    # The other direction: broader matching must not turn every edit into a
    # stale claim, or the signal is worth nothing.
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("def request():\n    return 1\n")
    (repo / "other").mkdir()
    (repo / "other" / "thing.py").write_text("A = 1\n")
    commit_all(repo, "two unrelated modules")
    init_layer(repo)
    _claim(repo, "The `pkg.request` helper returns 1.")
    commit_all(repo, "describe it")

    (repo / "other" / "thing.py").write_text("A = 2\n")
    commit_all(repo, "change something else entirely")
    assert report_for(repo, "read-next").status == FRESH


def test_module_path_shapes() -> None:
    assert freshness._module_path("src/flask/views.py") == "flask.views"
    assert freshness._module_path("pkg/__init__.py") == "pkg"
    assert freshness._module_path("tests/apps/flask.py") == "tests.apps.flask"
    assert freshness._qualifies("flask.views", "views")
    assert freshness._qualifies("flask.views", "flask.views")
    assert not freshness._qualifies("flask.views", "flask")
    assert not freshness._qualifies("", "anything")
