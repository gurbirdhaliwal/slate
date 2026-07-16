from pathlib import Path

from slate import context, generator, imports, scanner
from slate.cli import main

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def add_shared_package(repo: Path) -> None:
    shared = repo / "shared"
    shared.mkdir()
    (shared / "__init__.py").write_text("")
    (shared / "util.py").write_text("def helper():\n    return 1\n")
    (repo / "demo" / "cli.py").write_text(
        "from shared.util import helper\n\ndef main():\n    return helper()\n"
    )


def test_python_import_edges(repo: Path) -> None:
    add_shared_package(repo)
    scan = scanner.scan(repo)
    edges = imports.import_edges(scan)
    assert "shared" in edges["demo"]
    assert "demo" not in edges["shared"]


def test_js_relative_import_edges(repo: Path) -> None:
    web = repo / "web"
    web.mkdir()
    (web / "app.ts").write_text('import { helper } from "../lib/util";\n')
    lib = repo / "lib"
    lib.mkdir()
    (lib / "util.ts").write_text("export const helper = 1;\n")
    scan = scanner.scan(repo)
    edges = imports.import_edges(scan)
    assert "lib" in edges["web"]


def test_generated_doc_gets_dependency_suggestion(repo: Path) -> None:
    init_layer(repo)  # watches demo/**, tests/** — shared doesn't exist yet
    add_shared_package(repo)
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("modules"))
    suggestions = imports.suggest(repo, doc, scan)
    patterns = {s.pattern for s in suggestions}
    assert "shared/**" in patterns


def test_human_doc_gets_reference_suggestion(repo: Path) -> None:
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + "\nWorking in `demo/cli.py` today.\n")
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("read-next"))
    suggestions = imports.suggest(repo, doc, scan)
    assert any(s.pattern == "demo/**" for s in suggestions)


def test_no_duplicate_suggestions_for_covered_dirs(repo: Path) -> None:
    init_layer(repo)
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("modules"))
    # demo/** and tests/** already watched; nothing new exists
    assert imports.suggest(repo, doc, scan) == []


def test_cli_watches_apply(repo: Path, capsys) -> None:
    init_layer(repo)
    add_shared_package(repo)
    code = main(["-C", str(repo), "watches", "modules", "--apply"])
    out = capsys.readouterr().out
    assert code == 0
    assert "shared/**" in out
    doc = context.load(repo, context.spec_by_name("modules"))
    assert "shared/**" in doc.watches
