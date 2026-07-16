"""End-to-end: the workflow a user actually runs, through the real CLI."""

import json
from pathlib import Path

from slate.cli import main

from .conftest import commit_all


def run(repo: Path, *args: str, capsys=None) -> tuple[int, str]:
    code = main(["-C", str(repo), *args])
    out = capsys.readouterr().out if capsys else ""
    return code, out


def test_full_workflow(repo: Path, capsys) -> None:
    # 1. init generates the layer
    code, out = run(repo, "init", capsys=capsys)
    assert code == 0
    assert (repo / "AGENTS.md").exists()
    assert (repo / ".slate" / "modules.md").exists()

    # 2. init refuses to clobber an existing layer
    code, _ = run(repo, "init", capsys=capsys)
    assert code == 2

    commit_all(repo, "add context layer")

    # 3. everything fresh; --ci passes
    code, out = run(repo, "status", "--ci", capsys=capsys)
    assert code == 0
    assert "fresh" in out and "stale" not in out

    # 4. a code change lands → affected docs flagged, --ci fails
    (repo / "demo" / "billing.py").write_text("TAX = 0.1\n")
    commit_all(repo, "add billing")
    code, out = run(repo, "status", "--ci", capsys=capsys)
    assert code == 1
    assert "stale" in out
    assert "demo/billing.py" in out

    # 5. status --json is machine-readable
    code, out = run(repo, "status", "--json", capsys=capsys)
    docs = {d["doc"]: d for d in json.loads(out)}
    assert docs["modules"]["status"] == "stale"
    assert docs["read-next"]["status"] == "fresh"

    # 6. sync updates the generated docs and clears the flags
    code, out = run(repo, "sync", capsys=capsys)
    assert code == 0
    commit_all(repo, "sync context")
    code, out = run(repo, "status", "--ci", capsys=capsys)
    assert code == 0

    # 7. verify reports scores
    code, out = run(repo, "verify", "--json", capsys=capsys)
    assert code == 0
    scores = {d["doc"]: d["score"] for d in json.loads(out)}
    assert all(s >= 0.8 for s in scores.values()), scores

    # 8. read prints the first-read path in order
    code, out = run(repo, "read", "--paths", capsys=capsys)
    assert code == 0
    paths = out.strip().splitlines()
    assert paths[0] == "AGENTS.md"
    assert ".slate/read-next.md" in paths


def test_mark_reanchors_human_doc(repo: Path, capsys) -> None:
    run(repo, "init", capsys=capsys)
    commit_all(repo, "layer")
    path = repo / ".slate" / "decisions.md"
    path.write_text(path.read_text() + "\nDate: 2026-07-15\nDecision: test\n")
    commit_all(repo, "decision")
    code, _ = run(repo, "mark", "decisions", capsys=capsys)
    assert code == 0
    _, out = run(repo, "status", "--json", capsys=capsys)
    docs = {d["doc"]: d for d in json.loads(out)}
    assert docs["decisions"]["status"] == "fresh"


def test_unknown_doc_errors(repo: Path, capsys) -> None:
    run(repo, "init", capsys=capsys)
    code, _ = run(repo, "mark", "nonsense", capsys=capsys)
    assert code == 2


def test_status_without_layer_errors(repo: Path, capsys) -> None:
    code, _ = run(repo, "status", capsys=capsys)
    assert code == 2


def test_not_a_git_repo(tmp_path: Path, capsys) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    code = main(["-C", str(plain), "status"])
    assert code == 2


def test_human_edits_survive_sync(repo: Path, capsys) -> None:
    run(repo, "init", capsys=capsys)
    commit_all(repo, "layer")
    modules = repo / ".slate" / "modules.md"
    modules.write_text(
        modules.read_text().replace("## Notes (human)", "## Notes (human)\n\nKEEP-ME")
    )
    (repo / "demo" / "extra.py").write_text("x = 1\n")
    commit_all(repo, "change")
    run(repo, "sync", capsys=capsys)
    text = modules.read_text()
    assert "KEEP-ME" in text
    assert "extra" not in text.split("slate:auto")[0]  # regenerated block, not duplicated


def test_help_overview(tmp_path: Path, capsys) -> None:
    # help must work anywhere — even outside a git repo
    plain = tmp_path / "nowhere"
    plain.mkdir()
    code = main(["-C", str(plain), "help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "typical workflow" in out
    assert "slate agent enable claude" in out


def test_help_for_a_command(repo: Path, capsys) -> None:
    code = main(["-C", str(repo), "help", "sync"])
    out = capsys.readouterr().out
    assert code == 0
    assert "re-anchor" in out
    assert "--prose" in out


def test_help_unknown_command(repo: Path, capsys) -> None:
    code = main(["-C", str(repo), "help", "bogus"])
    err = capsys.readouterr().err
    assert code == 2
    assert "unknown command" in err
    assert "sync" in err  # lists the known commands
