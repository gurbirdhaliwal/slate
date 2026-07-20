"""The benchmark harness must run end to end on a real repo and produce
sane, internally consistent numbers — it's a public claim generator."""

import json
import subprocess
import sys
from pathlib import Path

from slate import generator, scanner

from .conftest import commit_all

SCRIPT = Path(__file__).resolve().parent.parent / "benchmarks" / "benchmark.py"


def run_benchmark(repo: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def test_benchmark_end_to_end(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")
    (repo / "demo" / "billing.py").write_text("TAX = 0.1\n")
    commit_all(repo, "add billing")

    results = run_benchmark(repo)

    s = results["session_start"]
    # Note: on a tiny fixture repo the fixed-size context layer can exceed
    # the exploration baseline — the advantage scales with repo size, so
    # only internal consistency is asserted here (real-repo numbers live
    # in benchmarks/RESULTS.md).
    assert s["slate_read"]["tokens"] > 0
    assert s["guided_exploration"]["tokens"] > 0
    assert s["full_repo_dump"]["files"] >= 1

    t = results["timings_measured"]
    assert all(v > 0 for v in t.values())

    h = results["history_replay"]
    # the billing commit touched watched code and must be counted
    assert h["commits_analyzed"] >= 1
    assert h["commits_that_staled_docs"] >= 1
    assert h["manual_ai_maintenance"]["input_tokens"] > 0
    assert h["slate_maintenance"]["cost_usd"] == 0.0


def test_benchmark_markdown_renders(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo)],
        capture_output=True, text=True, check=True,
    )
    assert "## 1. Session start" in proc.stdout
    assert "0 tokens" in proc.stdout
