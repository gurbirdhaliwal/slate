"""Dependency edges as tracked facts (Part C).

No new freshness code: because edges render into the auto-block, a changed
edge set makes the block regenerate differently and the existing machinery
flags and heals it. These tests prove that composition end to end, and pin the
determinism invariant — a flaky fact would manufacture false `stale`.
"""

from __future__ import annotations

from pathlib import Path

from slate import context, freshness, generator, scanner
from slate.context import FRESH, STALE

from .conftest import commit_all, git


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def report_for(repo: Path, name: str) -> freshness.DocReport:
    return {r.doc.spec.name: r for r in freshness.evaluate_all(repo)}[name]


def arch_block(repo: Path) -> str:
    return generator.auto_content(context.spec_by_name("architecture"), scanner.scan(repo))


def import_demo_from_tests(repo: Path, *extra: str) -> None:
    body = "".join(f"import {mod}\n" for mod in ("demo.engine", *extra))
    (repo / "tests" / "test_engine.py").write_text(body + "\ndef test_run():\n    assert True\n")


def test_edges_are_a_field_on_the_scan(repo: Path) -> None:
    import_demo_from_tests(repo)
    scan = scanner.scan(repo)
    assert scan.edges.get("tests") == {"demo"}


def test_edge_renders_into_the_architecture_auto_block(repo: Path) -> None:
    import_demo_from_tests(repo)
    block = arch_block(repo)
    assert "## Module boundaries (scanned)" in block
    assert "- `tests/` → `demo/`" in block


def test_no_edges_renders_a_stable_sentinel(repo: Path) -> None:
    # The fixture's tests/ imports nothing — the fact is still present.
    block = arch_block(repo)
    assert "## Module boundaries (scanned)" in block
    assert "_no cross-module imports detected_" in block


def test_rendering_is_deterministic_and_sorted(repo: Path) -> None:
    # tests/ imports two other top-level dirs → the targets must be sorted, not
    # left in set-iteration order (which str-hash randomization would flake).
    (repo / "lib").mkdir()
    (repo / "lib" / "helper.py").write_text("def h():\n    return 1\n")
    import_demo_from_tests(repo, "lib.helper")

    block = arch_block(repo)
    line = next(ln for ln in block.splitlines() if ln.startswith("- `tests/` →"))
    assert line == "- `tests/` → `demo/`, `lib/`"  # alphabetical, byte-exact
    assert arch_block(repo) == block  # identical bytes on a second scan


def test_new_cross_module_import_flips_stale_then_sync_heals(repo: Path) -> None:
    init_layer(repo)
    assert report_for(repo, "architecture").status == FRESH

    import_demo_from_tests(repo)  # tests/ now imports demo/ — a new edge
    r = report_for(repo, "architecture")
    assert r.status == STALE
    assert "tests/test_engine.py" in r.changed_watched

    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("architecture"))
    generator.sync_doc(doc, scan)
    commit_all(repo, "sync edges")
    assert report_for(repo, "architecture").status == FRESH
    assert "- `tests/` → `demo/`" in context.spec_by_name("architecture").path(repo).read_text()


def test_edge_line_inherits_per_claim_trust(repo: Path) -> None:
    # Part B composition: the changed edge is a generated claim, flagged
    # individually — not just a whole-doc amber.
    init_layer(repo)
    import_demo_from_tests(repo)
    r = report_for(repo, "architecture")
    edge_claims = [c for c in r.claims if c.kind == "generated" and "→" in c.text]
    assert any(c.status == STALE for c in edge_claims)


def test_intra_directory_import_is_not_an_edge(repo: Path) -> None:
    # demo/cli importing demo/engine stays inside demo/ — top-level-dir
    # granularity means no self-edge, no false precision.
    (repo / "demo" / "cli.py").write_text("import demo.engine\n\ndef main():\n    return 0\n")
    scan = scanner.scan(repo)
    assert scan.edges.get("demo", set()) == set()
