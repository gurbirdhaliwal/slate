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


# --------------------------------------------------------------------------
# agentbench E3 — the repair sweep's pre-registration


def _agentbench_spec():
    import importlib.util
    import sys as _sys
    path = (Path(__file__).resolve().parent.parent / "benchmarks" / "agentbench"
            / "spec.py")
    module_spec = importlib.util.spec_from_file_location("agentbench_spec", path)
    module = importlib.util.module_from_spec(module_spec)
    # Registered before exec: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, which is None for a module that is only
    # half-imported, and the failure surfaces as an AttributeError inside
    # dataclasses rather than anywhere near here.
    _sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


def test_seeded_claims_name_code() -> None:
    """The whole experiment rests on these being *claims*.

    `claims._emit` only emits a body unit that references code, so a seeded
    sentence with no backticked ref is invisible to `slate repair` — which is
    exactly how the plan's original design came to measure zero. A future edit
    that softens the prose must not be able to do that silently.
    """
    from slate.claims import human_claims

    spec = _agentbench_spec()
    assert spec.SEEDED_CLAIMS, "the E3 arms need seeded claims to have anything to repair"
    for claim_text in spec.SEEDED_CLAIMS:
        emitted = human_claims(f"## Current focus\n\n{claim_text}\n")
        refs = [r for c in emitted for r in c.refs]
        assert refs, f"seeded claim carries no code reference: {claim_text[:60]}"


def test_repair_verdict_needs_a_gap_not_a_level() -> None:
    """Revision 1 of repairbench passed a threshold on one arm and measured
    nothing. An arm that repairs everything must still fail if the control
    does too."""
    spec = _agentbench_spec()
    passed, failures = spec.repair_verdict(
        convergence_on=1.0, convergence_off=1.0,
        accepted=5, rejected=0, delivery=1.0)
    assert not passed
    assert any("no convergence" in f for f in failures)


def test_repair_verdict_voids_rather_than_fails_on_bad_delivery() -> None:
    spec = _agentbench_spec()
    _, failures = spec.repair_verdict(1.0, 0.0, 5, 0, delivery=0.0)
    assert any("VOID" in f for f in failures)


def test_repair_verdict_keeps_the_plans_kill_criterion() -> None:
    """"If verified repairs do not exceed rejections ... the pivot failed"."""
    spec = _agentbench_spec()
    passed, failures = spec.repair_verdict(1.0, 0.0, 2, 2, 1.0)
    assert not passed
    assert any("costs more than it returns" in f for f in failures)


def test_delivery_gate_ignores_correct_silence() -> None:
    """A hook that stays quiet on an already-clean layer is working, not broken.

    Revision 1 of the E3 gate counted injections over every repair-on trial,
    read 50%, and voided a sweep in which the hook had spoken every time it had
    anything to speak about.
    """
    spec = _agentbench_spec()
    records = [
        {"stop_hook_injected": 1, "suspect_claims_end": 0},  # spoke, then fixed
        {"stop_hook_injected": 0, "suspect_claims_end": 0},  # nothing to say
        {"stop_hook_injected": 0, "suspect_claims_end": 0},  # nothing to say
    ]
    rate, delivered, relevant = spec.delivery_rate(records)
    assert (delivered, relevant) == (1, 1)
    assert rate == 1.0


def test_delivery_gate_still_catches_a_silent_hook_with_work_pending() -> None:
    """The case revision 1 could not see: silence *and* a claim left suspect."""
    spec = _agentbench_spec()
    records = [
        {"stop_hook_injected": 1, "suspect_claims_end": 0},
        {"stop_hook_injected": 0, "suspect_claims_end": 2},  # genuinely failed
    ]
    rate, delivered, relevant = spec.delivery_rate(records)
    assert (delivered, relevant) == (1, 2)
    assert rate == 0.5
    passed, failures = spec.repair_verdict(1.0, 0.0, 5, 0, rate)
    assert not passed and any("VOID" in f for f in failures)


def test_e3_delivery_threshold_did_not_move() -> None:
    """Revision 2 fixed the denominator. Moving the bar as well would be
    choosing the criterion to fit the result."""
    spec = _agentbench_spec()
    assert spec.MIN_DELIVERY == 0.90
    assert spec.MIN_CONVERGENCE_GAP == 0.30
