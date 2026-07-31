"""Co-change coupling — facts from history rather than from the tree.

Why this exists: the agent benchmark found a fresh Slate layer changed
nothing about how an agent worked, because everything in it — file counts,
module boundaries, import edges — is rederivable from the checkout in two or
three tool calls. History is the one thing that is not, and across 15
measured sessions no agent ran `git log`, `git blame` or `git show` once.

Most of these tests pin *selection quality*, not correctness of counting.
That is deliberate: a co-change table is trivially easy to make true and
quite hard to make useful, and both ways of getting it wrong were observed on
real repos before being fixed here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slate import cochange, context, scanner

from .conftest import commit_all, git


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def couple(repo: Path, files: list[str], times: int, tag: str = "c") -> None:
    """Change these files together, `times` times."""
    for i in range(times):
        for rel in files:
            write(repo, rel, f"# {tag}{i}\nvalue = {i}\n")
        commit_all(repo, f"{tag}-{i}")


def _files(repo: Path) -> list[str]:
    from slate import gitutil
    return gitutil.list_files(repo)


def pairs(repo: Path, **kw) -> list[tuple[str, str]]:
    return cochange.compute(repo, _files(repo), **kw)


# --- the basic fact ---------------------------------------------------------

def test_files_changed_together_are_reported(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=4)
    assert ("demo/a.py", "demo/b.py") in pairs(repo)


def test_files_never_changed_together_are_not(repo: Path) -> None:
    couple(repo, ["demo/a.py"], times=4, tag="a")
    couple(repo, ["demo/b.py"], times=4, tag="b")
    assert ("demo/a.py", "demo/b.py") not in pairs(repo)


def test_a_single_shared_commit_is_not_a_fact(repo: Path) -> None:
    # One commit touching two files is a coincidence, not coupling.
    couple(repo, ["demo/a.py", "demo/b.py"], times=1)
    assert pairs(repo) == []


def test_pairs_are_ordered_and_deduplicated(repo: Path) -> None:
    couple(repo, ["demo/b.py", "demo/a.py"], times=4)
    result = pairs(repo)
    assert result == [("demo/a.py", "demo/b.py")]
    for a, b in result:
        assert a < b


# --- determinism: a flaky fact manufactures a false `stale` -----------------

def test_output_is_deterministic(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=4)
    couple(repo, ["demo/c.py", "demo/d.py"], times=4, tag="d")
    assert pairs(repo) == pairs(repo)


def test_output_is_stable_across_hash_seeds(repo: Path) -> None:
    """The block is diffed to decide freshness, so byte-identical output for
    identical history is load-bearing, not cosmetic."""
    import json
    import subprocess
    import sys

    couple(repo, ["demo/a.py", "demo/b.py"], times=4)
    couple(repo, ["demo/c.py", "demo/d.py"], times=4, tag="d")
    script = (
        "import json,sys;"
        "from pathlib import Path;"
        "from slate import cochange, gitutil;"
        "r=Path(sys.argv[1]);"
        "print(json.dumps(cochange.compute(r, gitutil.list_files(r))))"
    )
    outs = []
    for seed in ("0", "1", "42"):
        proc = subprocess.run(
            [sys.executable, "-c", script, str(repo)],
            capture_output=True, text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            cwd=Path(__file__).resolve().parents[1],
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(json.loads(proc.stdout))
    assert outs[0] == outs[1] == outs[2]


# --- selection quality: the two ways this goes wrong ------------------------

def test_hub_files_do_not_crowd_out_specific_coupling(repo: Path) -> None:
    """A file touched by nearly every commit must not win every slot.

    Observed on Flask: ranked by raw co-occurrence, six of twelve slots went
    to `CHANGES.rst` paired with whatever else that commit happened to touch,
    and the pair a reader actually needed was pushed out entirely.
    """
    # `hub.py` changes with everything; a.py/b.py change specifically together.
    for i in range(12):
        write(repo, "demo/hub.py", f"hub = {i}\n")
        write(repo, f"demo/mod{i % 6}.py", f"x = {i}\n")
        commit_all(repo, f"hub-{i}")
    couple(repo, ["demo/a.py", "demo/b.py"], times=5, tag="spec")

    result = pairs(repo)
    assert ("demo/a.py", "demo/b.py") in result, (
        "specific coupling was crowded out by the hub file")
    hub_share = sum(1 for a, b in result if "hub.py" in (a, b))
    assert hub_share <= len(result) // 2


def test_rare_pairs_do_not_outrank_frequent_ones(repo: Path) -> None:
    """Jaccard alone ranks two files edited twice, always together, above a
    pair that co-changed forty times. Observed on Flask, where it evicted the
    ground-truth pair in favour of docs."""
    couple(repo, ["demo/rare1.py", "demo/rare2.py"], times=3, tag="rare")
    couple(repo, ["demo/hot1.py", "demo/hot2.py"], times=15, tag="hot")

    result = pairs(repo, top_k=1)
    assert result == [("demo/hot1.py", "demo/hot2.py")]


def test_bulk_commits_do_not_manufacture_coupling(repo: Path) -> None:
    """A reformat touching everything couples every pair of files it swept up."""
    for i in range(40):
        write(repo, f"demo/mass{i}.py", "x = 'initial'\n")
    commit_all(repo, "add many")
    for round_ in range(4):  # a repeated sweep over all of them
        for i in range(40):
            write(repo, f"demo/mass{i}.py", f"x = {round_}\n")
        commit_all(repo, f"reformat-{round_}")

    result = pairs(repo)
    swept = [p for p in result if "mass" in p[0] and "mass" in p[1]]
    assert not swept, f"bulk commit invented coupling: {swept[:3]}"


# --- exclusions -------------------------------------------------------------

def test_the_context_layer_is_excluded(repo: Path) -> None:
    """`slate sync` rewrites every generated doc in one commit, making the
    layer the most tightly coupled group of files in any Slate repo. Left in,
    it wins every slot and the table says only that Slate docs change with
    Slate docs."""
    from slate import generator

    for i in range(5):
        generator.generate_all(scanner.scan(repo))
        write(repo, "demo/a.py", f"x = {i}\n")
        commit_all(repo, f"sync-{i}")

    for a, b in pairs(repo):
        assert a not in context.CONTEXT_DOC_PATHS
        assert b not in context.CONTEXT_DOC_PATHS


def test_non_code_files_are_excluded(repo: Path) -> None:
    # "What else must I change?" is a code question. Changelog and CI coupling
    # is real but is release hygiene, and it drowns the source signal.
    couple(repo, ["CHANGES.md", "demo/a.py"], times=6, tag="doc")
    for a, b in pairs(repo):
        assert a.endswith(".py") and b.endswith(".py")


def test_deleted_files_are_not_reported(repo: Path) -> None:
    couple(repo, ["demo/gone.py", "demo/a.py"], times=5)
    (repo / "demo" / "gone.py").unlink()
    commit_all(repo, "delete")
    for a, b in pairs(repo):
        assert "gone.py" not in (a, b)


# --- never break the scan ---------------------------------------------------

def test_repo_without_history_yields_no_facts(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "-q")
    assert cochange.compute(root, []) == []


def test_git_failure_is_survivable(repo: Path, monkeypatch) -> None:
    """A scan must not die because history is unreadable (shallow clone,
    missing git, corrupt object)."""
    from slate import gitutil

    def boom(*_a, **_k):
        raise gitutil.GitError("no history here")

    monkeypatch.setattr(gitutil, "_git", boom)
    assert cochange.compute(repo, ["demo/a.py"]) == []


def test_scan_exposes_cochange_when_enabled(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv(cochange.ENABLED_ENV, "1")
    couple(repo, ["demo/a.py", "demo/b.py"], times=4)
    assert ("demo/a.py", "demo/b.py") in scanner.scan(repo).cochange


def test_scan_omits_cochange_by_default(repo: Path, monkeypatch) -> None:
    """Off by default on the evidence: measured twice against `bare` and it
    moved nothing, while costing 46% more context (p=0.0411). The code stays
    for a future re-measurement; it does not ship on."""
    monkeypatch.delenv(cochange.ENABLED_ENV, raising=False)
    couple(repo, ["demo/a.py", "demo/b.py"], times=4)
    assert scanner.scan(repo).cochange == []


def test_top_k_is_respected(repo: Path) -> None:
    for i in range(8):
        couple(repo, [f"demo/x{i}.py", f"demo/y{i}.py"], times=4, tag=f"g{i}")
    assert len(pairs(repo, top_k=3)) == 3


# --- per-file partners (what the PreToolUse hook asks for) ------------------

def test_partners_names_the_coupled_file(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=5)
    names = [p for p, _ in cochange.partners(repo, _files(repo), "demo/a.py")]
    assert "demo/b.py" in names


def test_partners_reports_the_count(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=5)
    got = dict(cochange.partners(repo, _files(repo), "demo/a.py"))
    assert got["demo/b.py"] >= 3


def test_partners_is_symmetric(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=5)
    assert "demo/a.py" in [p for p, _ in cochange.partners(repo, _files(repo), "demo/b.py")]


def test_partners_never_includes_the_file_itself(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=5)
    assert all(p != "demo/a.py" for p, _ in cochange.partners(repo, _files(repo), "demo/a.py"))


def test_partners_surfaces_coupling_below_the_rendered_top_k(repo: Path) -> None:
    """The per-file view exists because the rendered table is a repo-wide
    top-twelve: a real coupling ranked thirteenth appears nowhere in the doc,
    but is exactly what someone editing that file needs."""
    for i in range(14):
        couple(repo, [f"demo/hot{i}.py", f"demo/hot{i}b.py"], times=9, tag=f"h{i}")
    # Six rather than the bare minimum. For a pair that always moves together
    # `count x jaccard` reduces to the raw count, so six still ranks below the
    # hot pairs' nine while leaving three commits of slack above MIN_COUNT.
    # At four there was no slack: this test failed once on CI and passed on
    # re-run at the same commit, and two miscounted commits are the whole
    # margin between "ranked fifteenth" and "invisible".
    couple(repo, ["demo/quiet.py", "demo/partner.py"], times=6, tag="q")

    # Guard the fixture before the behaviour. With min_count=1 selection
    # cannot be what hides the pair, so a failure here says the commits did
    # not land as intended — a flake in the harness, not in the selector.
    built = dict(cochange.partners(repo, _files(repo), "demo/quiet.py", min_count=1))
    assert built.get("demo/partner.py", 0) >= cochange.MIN_COUNT, (
        f"fixture produced {built.get('demo/partner.py', 0)} co-changes for the "
        f"quiet pair, under the {cochange.MIN_COUNT} selection requires: {built}")

    assert ("demo/partner.py", "demo/quiet.py") not in cochange.compute(repo, _files(repo))
    assert "demo/partner.py" in [
        p for p, _ in cochange.partners(repo, _files(repo), "demo/quiet.py")]


def test_partners_is_silent_for_an_uncoupled_file(repo: Path) -> None:
    couple(repo, ["demo/a.py", "demo/b.py"], times=5)
    assert cochange.partners(repo, _files(repo), "demo/cli.py") == []


def test_partners_survives_unreadable_history(repo: Path, monkeypatch) -> None:
    from slate import gitutil

    def boom(*_a, **_k):
        raise gitutil.GitError("nope")

    monkeypatch.setattr(gitutil, "_git", boom)
    assert cochange.partners(repo, ["demo/a.py"], "demo/a.py") == []
