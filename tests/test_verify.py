from pathlib import Path

from slate import generator, scanner, verify
from slate.verify import extract_path_refs

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def score_for(repo: Path, name: str) -> verify.Verification:
    return {v.report.doc.spec.name: v for v in verify.verify_all(repo)}[name]


def test_extract_path_refs():
    body = (
        "See [`demo/cli.py`](demo/cli.py) and `tests/test_x.py`.\n"
        "Not a path: `main`, [docs](https://example.com), #anchor.\n"
        "Root file: `Makefile`.\n"
    )
    refs = extract_path_refs(body)
    assert "demo/cli.py" in refs
    assert "tests/test_x.py" in refs
    assert "Makefile" in refs
    assert not any("example.com" in r for r in refs)
    assert "main" not in refs


def test_fresh_layer_scores_high(repo: Path) -> None:
    init_layer(repo)
    for v in verify.verify_all(repo):
        assert v.score >= 0.9, (v.rel_path, v.score, v.missing)


def test_missing_reference_drops_score(repo: Path) -> None:
    init_layer(repo)
    baseline = score_for(repo, "read-next").score
    path = repo / ".slate" / "read-next.md"
    path.write_text(path.read_text() + "\nWorking in `demo/deleted_file.py` today.\n")
    v = score_for(repo, "read-next")
    assert "demo/deleted_file.py" in v.missing
    assert v.score < baseline


def test_watched_changes_drop_score(repo: Path) -> None:
    init_layer(repo)
    baseline = score_for(repo, "modules").score
    for i in range(3):
        (repo / "demo" / f"gen_{i}.py").write_text("x = 1\n")
    v = score_for(repo, "modules")
    assert v.score < baseline


def orphan_anchor(repo: Path, doc: str, strip_digest: bool = False) -> None:
    path = repo / ".slate" / f"{doc}.md"
    text = path.read_text().replace("slate_synced_commit: ", "slate_synced_commit: deadbee")
    if strip_digest:
        text = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("slate_synced_digest")
        ) + "\n"
    path.write_text(text)


def test_unverifiable_doc_is_capped(repo: Path) -> None:
    init_layer(repo)
    orphan_anchor(repo, "modules", strip_digest=True)
    assert score_for(repo, "modules").score <= 0.25


def test_digest_recovered_doc_is_not_capped(repo: Path) -> None:
    # Orphaned anchor + matching content digest = provably current, so the
    # squash-merge workflow must not tank the score.
    init_layer(repo)
    orphan_anchor(repo, "modules")
    v = score_for(repo, "modules")
    assert v.report.status == "fresh"
    assert v.score >= 0.9


def test_digest_mismatch_scores_as_known_stale(repo: Path) -> None:
    init_layer(repo)
    orphan_anchor(repo, "modules")
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    v = score_for(repo, "modules")
    assert v.report.status == "stale"
    assert v.score <= 0.5


def test_content_verified_change_keeps_score_high(repo: Path) -> None:
    # A watched edit that doesn't change the scanned facts takes no
    # watch-quiet penalty — "stale noise" must not erode trust either.
    init_layer(repo)
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    v = score_for(repo, "modules")
    assert v.report.status == "fresh"
    assert v.report.content_verified
    assert v.score >= 0.9
