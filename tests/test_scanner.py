from pathlib import Path

from slate import scanner


def test_scan_finds_modules_languages_and_commands(repo: Path) -> None:
    scan = scanner.scan(repo)
    assert scan.readme_title == "Demo Project"
    assert set(scan.source_dirs) == {"demo", "tests"}
    assert scan.languages["Python"] >= 4
    assert "make test" in scan.commands["make"]
    assert scan.commands["console scripts"] == ["demo"]


def test_scan_reflects_working_tree_not_index(repo: Path) -> None:
    # A file deleted on disk but not yet staged is still in git's index;
    # the scan must describe what actually exists.
    (repo / "demo" / "engine.py").unlink()
    scan = scanner.scan(repo)
    assert "demo/engine.py" not in scan.files


def test_untracked_files_are_scanned(repo: Path) -> None:
    newpkg = repo / "newpkg"
    newpkg.mkdir()
    (newpkg / "core.py").write_text("x = 1\n")
    scan = scanner.scan(repo)
    assert "newpkg" in scan.source_dirs
