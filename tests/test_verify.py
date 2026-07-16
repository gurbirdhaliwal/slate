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


def test_unverifiable_doc_is_capped(repo: Path) -> None:
    init_layer(repo)
    path = repo / ".slate" / "modules.md"
    text = path.read_text().replace("slate_synced_commit: ", "slate_synced_commit: deadbee")
    path.write_text(text)
    assert score_for(repo, "modules").score <= 0.25
