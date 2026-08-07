from pathlib import Path

from slate import context, diffs, generator, scanner
from slate.cli import main

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def diff_for(repo: Path, name: str) -> diffs.DocDiff:
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name(name))
    return diffs.doc_diff(repo, doc, scan)


def test_change_kinds_reported(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "newmod.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "demo" / "engine.py").unlink()
    d = diff_for(repo, "modules")
    assert d.changes["demo/newmod.py"] == "A"
    assert d.changes["demo/engine.py"] == "D"


def test_sync_preview_shows_auto_block_diff(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "add extra")
    d = diff_for(repo, "modules")
    assert d.sync_preview, "expected a unified diff of the auto block"
    joined = "\n".join(d.sync_preview)
    assert "-| `demo/` | 3 |" in joined
    assert "+| `demo/` | 4 |" in joined


def test_missing_reference_is_a_broken_claim(repo: Path) -> None:
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text(encoding="utf-8") + "\nSee `demo/engine.py` for the core.\n", encoding="utf-8")
    (repo / "demo" / "engine.py").unlink()
    d = diff_for(repo, "read-next")
    assert "demo/engine.py" in d.missing_refs


def test_fresh_layer_diffs_nothing(repo: Path, capsys) -> None:
    init_layer(repo)
    code = main(["-C", str(repo), "diff"])
    assert code == 0
    assert "everything fresh" in capsys.readouterr().out


def test_cli_diff_output(repo: Path, capsys) -> None:
    init_layer(repo)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    code = main(["-C", str(repo), "diff"])
    out = capsys.readouterr().out
    assert code == 0
    assert "watched changes:" in out
    assert "demo/extra.py" in out
