import json
from pathlib import Path

from slate import generator, scanner
from slate.cli import main

from .conftest import commit_all, git


def make_repo(parent: Path, name: str, with_layer: bool) -> Path:
    root = parent / name
    (root / "src").mkdir(parents=True)
    git(root, "init", "-q")
    (root / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(root, "init")
    if with_layer:
        generator.generate_all(scanner.scan(root))
        commit_all(root, "layer")
    return root


def test_fleet_rollup(tmp_path: Path, capsys) -> None:
    make_repo(tmp_path, "alpha", with_layer=True)
    make_repo(tmp_path, "beta", with_layer=False)
    code = main(["fleet", str(tmp_path), "--json"])
    assert code == 0
    rows = {Path(r["repo"]).name: r for r in json.loads(capsys.readouterr().out)}
    assert rows["alpha"]["layer"] is True
    assert rows["alpha"]["fresh"] == 6
    assert rows["alpha"]["stale"] == 0
    assert rows["beta"]["layer"] is False


def test_fleet_ci_fails_on_stale_repo(tmp_path: Path, capsys) -> None:
    alpha = make_repo(tmp_path, "alpha", with_layer=True)
    (alpha / "src" / "new.py").write_text("y = 2\n", encoding="utf-8")  # stales alpha's docs
    assert main(["fleet", str(tmp_path), "--ci"]) == 1
    assert main(["fleet", str(tmp_path)]) == 0  # without --ci it only reports


def test_fleet_accepts_explicit_repo_paths(tmp_path: Path, capsys) -> None:
    alpha = make_repo(tmp_path, "alpha", with_layer=True)
    code = main(["fleet", str(alpha)])
    out = capsys.readouterr().out
    assert code == 0
    assert "fresh 6" in out


def test_fleet_no_repos_found(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["fleet", str(empty)]) == 2
