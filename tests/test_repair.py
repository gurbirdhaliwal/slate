"""Repair tasks — the worklist behind the pivot, and what it must not claim.

These pin two things the rest of the arc depends on: that a task points at a
place someone can open, and that a task is never mistaken for proof the prose
is wrong. Most flagged claims on real history were still accurate.
"""

from __future__ import annotations

from pathlib import Path

from slate import context, freshness, generator, repair, scanner

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def claim(repo: Path, text: str) -> None:
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + f"\n{text}\n")


def tasks(repo: Path) -> list[repair.RepairTask]:
    return repair.repair_tasks(repo, freshness.evaluate_all(repo))


def test_a_fresh_layer_has_nothing_to_repair(repo: Path) -> None:
    init_layer(repo)
    assert tasks(repo) == []


def test_generated_drift_is_not_a_repair_task(repo: Path) -> None:
    # `slate sync` rewrites the auto-block deterministically for zero tokens.
    # Routing that to a model would be strictly worse than the machinery that
    # already fixes it — measured over this repo's history, generated drift
    # was the *only* staleness that ever occurred.
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    commit_all(repo, "new file changes the module map")
    assert any(r.status != "fresh" for r in freshness.evaluate_all(repo))
    assert all(t.doc_path != ".slate/modules.md" for t in tasks(repo))


def test_task_points_at_a_line_someone_can_open(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    lines = (repo / task.doc_path).read_text().splitlines()
    assert "engine.run" in lines[task.line - 1]  # 1-based, and into the *file*
    assert task.section
    assert task.anchor


def test_symbol_evidence_outranks_file_evidence(repo: Path) -> None:
    # A path ref only says a file changed somewhere; a symbol ref says the
    # named thing moved. The strong evidence has to come first, because that
    # is where a reader should start.
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    claim(repo, "Helpers live in `demo/helper.py`.")
    (repo / "demo" / "helper.py").write_text("def a():\n    return 1\n")
    commit_all(repo, "describe both")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    (repo / "demo" / "helper.py").write_text("def a():\n    return 2\n")
    commit_all(repo, "change both")

    got = tasks(repo)
    assert [t.scope for t in got] == ["symbol", "path"]
    assert got[0].evidence_is_strong and not got[1].evidence_is_strong


def test_a_task_carries_the_commit_behind_it(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    sha = commit_all(repo, "change run")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    assert task.commits["engine.run"].startswith(sha)
    assert task.uncommitted == []


def test_an_uncommitted_change_says_so_rather_than_going_silent(repo: Path) -> None:
    # "No commit" is not "no evidence" — the file is among the hits either
    # way. The distinction is whether the diff is `git show` or `git diff`.
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    assert task.commits == {}
    assert task.uncommitted == ["engine.run"]


def test_json_shape_is_complete(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run")

    payload = tasks(repo)[0].as_dict()
    assert set(payload) == {
        "doc_path", "line", "end_line", "section", "text", "status",
        "scope", "risk", "anchor", "commits", "uncommitted",
    }


def test_claim_verdicts_stay_backward_compatible(repo: Path) -> None:
    # status/verify/diff and the MCP surface all read this shape; the new
    # fields are additive, exactly as the Part B rollout was.
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    report = next(r for r in freshness.evaluate_all(repo) if r.claims)
    payload = report.claims[0].as_dict()
    assert {"text", "section", "kind", "status", "refs", "risk"} <= set(payload)
