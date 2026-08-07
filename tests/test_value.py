"""Value ledger: measured receipts, catch dedupe, and `slate value`."""

from __future__ import annotations

import json
from pathlib import Path

from slate import repair, value
from slate.cli import main
from slate.mcp import SlateMCPServer

from .conftest import commit_all


def run(repo: Path, *args: str, capsys=None) -> tuple[int, str]:
    code = main(["-C", str(repo), *args])
    out = capsys.readouterr().out if capsys else ""
    return code, out


def _init(repo: Path, capsys) -> None:
    run(repo, "init", capsys=capsys)
    commit_all(repo, "add context layer")


def _ledger(repo: Path) -> dict:
    return json.loads(value.ledger_path(repo).read_text(encoding="utf-8"))


def _stale_change(repo: Path, name: str = "billing") -> None:
    (repo / "demo" / f"{name}.py").write_text("TAX = 0.1\n", encoding="utf-8")
    commit_all(repo, f"add {name}")


def call_tool(server: SlateMCPServer, name: str, args: dict | None = None) -> dict:
    response = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    })
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


# --- session receipts --------------------------------------------------------

def test_read_records_measured_session(repo: Path, capsys) -> None:
    _init(repo, capsys)
    code, out = run(repo, "read", capsys=capsys)
    assert code == 0
    assert "value:" in out  # the one-line receipt

    data = _ledger(repo)
    assert data["sessions"]["count"] == 1
    assert data["sessions"]["context_tokens"] > 0
    assert data["sessions"]["baseline_tokens"] > 0

    run(repo, "read", capsys=capsys)
    assert _ledger(repo)["sessions"]["count"] == 2


def test_read_paths_output_stays_machine_consumable(repo: Path, capsys) -> None:
    _init(repo, capsys)
    _, out = run(repo, "read", "--paths", capsys=capsys)
    assert all(line.endswith(".md") for line in out.strip().splitlines())
    assert _ledger(repo)["sessions"]["count"] == 1  # still recorded


def test_ledger_lives_outside_the_working_tree(repo: Path, capsys) -> None:
    _init(repo, capsys)
    run(repo, "read", capsys=capsys)
    path = value.ledger_path(repo)
    assert path.exists()
    assert str(path).startswith(str(repo / ".git"))
    # Recording value must never stale a doc.
    code, _ = run(repo, "status", "--ci", capsys=capsys)
    assert code == 0


# --- stale catches -----------------------------------------------------------

def test_status_catches_dedupe_per_doc_and_anchor(repo: Path, capsys) -> None:
    _init(repo, capsys)
    _stale_change(repo)
    _, out = run(repo, "status", capsys=capsys)
    assert "value: caught" in out
    first = _ledger(repo)["catches"]["count"]
    assert first > 0

    # Re-checking the same staleness is not a new catch — and no footer noise.
    _, out = run(repo, "status", capsys=capsys)
    assert "value: caught" not in out
    assert _ledger(repo)["catches"]["count"] == first

    # Healing and re-staling on a new anchor is a new catch.
    run(repo, "sync", capsys=capsys)
    commit_all(repo, "sync context")
    _stale_change(repo, "shipping")
    run(repo, "status", capsys=capsys)
    assert _ledger(repo)["catches"]["count"] > first


def test_status_json_stays_parseable(repo: Path, capsys) -> None:
    _init(repo, capsys)
    _stale_change(repo)
    _, out = run(repo, "status", "--json", capsys=capsys)
    docs = {d["doc"]: d for d in json.loads(out)}  # no footer mixed in
    assert docs["modules"]["status"] == "stale"
    assert _ledger(repo)["catches"]["count"] > 0  # recorded silently


# --- sync receipts -----------------------------------------------------------

def test_sync_measures_the_manual_alternative(repo: Path, capsys) -> None:
    _init(repo, capsys)
    _stale_change(repo)
    _, out = run(repo, "sync", capsys=capsys)
    assert "value: healed" in out
    assert "0 tokens" in out

    data = _ledger(repo)["syncs"]
    assert data["count"] == 1
    assert data["healed_docs"] >= 1
    assert data["manual_input_tokens"] > 0
    assert data["manual_output_tokens"] > 0
    assert data["measured_ms"] > 0

    # A pure re-anchor of fresh docs saves nothing and claims nothing.
    commit_all(repo, "sync context")
    _, out = run(repo, "sync", capsys=capsys)
    assert "value:" not in out
    after = _ledger(repo)["syncs"]
    assert after["count"] == 2
    assert after["manual_input_tokens"] == data["manual_input_tokens"]


# --- the value command -------------------------------------------------------

def test_value_command_reports_measured_and_estimated(repo: Path, capsys) -> None:
    _init(repo, capsys)
    run(repo, "read", capsys=capsys)
    _stale_change(repo)
    run(repo, "status", capsys=capsys)
    run(repo, "sync", capsys=capsys)

    code, out = run(repo, "value", capsys=capsys)
    assert code == 0
    assert "measured" in out and "estimated" in out
    assert "chars/token" in out  # assumptions are always disclosed

    _, out = run(repo, "value", "--json", capsys=capsys)
    t = json.loads(out)
    assert t["measured"]["sessions_served"] == 1
    assert t["measured"]["stale_docs_caught"] > 0
    assert t["measured"]["sync_tokens_spent"] == 0
    assert t["estimated"]["maintenance_input_tokens_avoided"] > 0
    assert t["assumptions"]["chars_per_token"] == value.CHARS_PER_TOKEN
    # The estimate is arithmetic over the measured sums, nothing else.
    m, e = t["measured"], t["estimated"]
    assert e["session_input_tokens_avoided"] == (
        m["exploration_baseline_tokens"] - m["context_tokens_served"]
    )


def test_value_command_with_no_history(repo: Path, capsys) -> None:
    _init(repo, capsys)
    code, out = run(repo, "value", capsys=capsys)
    assert code == 0
    assert "no value recorded" in out


# --- opt-out and resilience --------------------------------------------------

def test_disabled_via_env(repo: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("SLATE_NO_VALUE", "1")
    _init(repo, capsys)
    _, out = run(repo, "read", capsys=capsys)
    assert "value:" not in out
    assert not value.ledger_path(repo).exists()


def test_corrupt_ledger_never_breaks_a_command(repo: Path, capsys) -> None:
    _init(repo, capsys)
    path = value.ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    code, _ = run(repo, "read", capsys=capsys)
    assert code == 0
    assert _ledger(repo)["sessions"]["count"] == 1  # healed to a fresh ledger


# --- MCP surface -------------------------------------------------------------

def test_mcp_read_carries_value_receipt(repo: Path, capsys) -> None:
    _init(repo, capsys)
    payload = call_tool(SlateMCPServer(repo), "slate_read")
    assert payload["value"]["context_tokens"] > 0
    assert payload["value"]["exploration_baseline_tokens"] > 0
    assert "measured" in payload["value"]["note"]
    assert _ledger(repo)["sessions"]["count"] == 1


def test_mcp_sync_carries_value_receipt(repo: Path, capsys) -> None:
    _init(repo, capsys)
    _stale_change(repo)
    payload = call_tool(SlateMCPServer(repo, access="full"), "slate_sync")
    assert payload["value"]["tokens_spent"] == 0
    assert payload["value"]["healed_stale_docs"]
    assert payload["value"]["manual_rewrite_tokens_measured"]["input"] > 0
    assert _ledger(repo)["syncs"]["healed_docs"] >= 1


# --- repairs (Phase 5) ------------------------------------------------------


def test_repair_ledger_counts_both_outcomes(repo: Path) -> None:
    value.record_repair(repo, repair.REPAIRED)
    value.record_repair(repo, repair.REPAIRED)
    value.record_repair(repo, repair.REJECTED)
    measured = value.totals(repo)["measured"]
    assert measured["repairs_verified"] == 2
    assert measured["repairs_refused"] == 1


def test_an_accurate_claim_left_alone_is_not_a_gate_event(repo: Path) -> None:
    # `unchanged` is the correct outcome on a flagged-but-accurate claim, and
    # it was the right answer in half of repairbench rev 3's trials. Counting
    # it as a repair would inflate the ledger with non-events.
    value.record_repair(repo, repair.UNCHANGED)
    assert value.totals(repo)["measured"]["repairs_verified"] == 0
    assert value.totals(repo)["measured"]["repairs_refused"] == 0


def test_repair_ledger_never_breaks_the_caller(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(value, "_load", lambda *_: (_ for _ in ()).throw(RuntimeError))
    assert value.record_repair(repo, repair.REPAIRED) is None


def test_repair_ledger_survives_an_older_ledger_without_the_section(repo: Path) -> None:
    value.record_repair(repo, repair.REPAIRED)
    path = value.ledger_path(repo)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["repairs"]                    # a ledger written before Phase 5
    path.write_text(json.dumps(data), encoding="utf-8")
    # Heals to an empty section instead of raising — the same contract the
    # other sections have had since the ledger shipped.
    assert value.record_repair(repo, repair.REPAIRED) == {"verified": 1, "refused": 0}


def test_value_report_states_what_repairs_do_not_prove(repo: Path) -> None:
    """The report must not let a repair count read as 'the layer stayed fresh
    because of Slate' — a control with no repair loop converged 36-69% of the
    time, so that attribution is not available."""
    value.record_repair(repo, repair.REPAIRED)
    report = value.render_report(value.totals(repo))
    assert "repairs verified" in report.lower()
    assert "36-69%" in report
