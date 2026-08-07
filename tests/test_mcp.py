"""MCP server: handshake, tool listing per access mode, and every tool.

The server is exercised through ``handle`` (the full JSON-RPC path minus
the stdio loop) against real git repos — same fixture as everything else.
"""

import io
import json
from pathlib import Path

from slate import agentcfg, context, generator, scanner
from slate.mcp import SlateMCPServer, replace_section, serve

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def call(server: SlateMCPServer, name: str, arguments: dict | None = None) -> tuple[dict, bool]:
    resp = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })
    result = resp["result"]
    text = result["content"][0]["text"]
    try:
        return json.loads(text), result["isError"]
    except json.JSONDecodeError:
        return {"text": text}, result["isError"]


def list_tools(server: SlateMCPServer) -> list[str]:
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return [t["name"] for t in resp["result"]["tools"]]


def test_initialize_handshake(repo: Path) -> None:
    server = SlateMCPServer(repo)
    resp = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    result = resp["result"]
    assert result["serverInfo"]["name"] == "slate"
    assert "tools" in result["capabilities"]
    # notifications get no response
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_read_mode_hides_write_tools(repo: Path) -> None:
    init_layer(repo)
    tools = list_tools(SlateMCPServer(repo))  # default access: read
    assert "slate_read" in tools and "slate_status" in tools
    assert not any(t in tools for t in ("slate_sync", "slate_mark", "slate_update_focus"))


def test_full_mode_exposes_write_tools(repo: Path) -> None:
    init_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    tools = list_tools(SlateMCPServer(repo))
    assert {"slate_sync", "slate_mark", "slate_update_focus", "slate_append_decision"} <= set(tools)


def test_write_call_denied_in_read_mode(repo: Path) -> None:
    init_layer(repo)
    payload, is_error = call(SlateMCPServer(repo), "slate_sync")
    assert is_error
    assert "read-only" in payload["text"]


def test_access_toggle_applies_without_restart(repo: Path) -> None:
    init_layer(repo)
    server = SlateMCPServer(repo)
    _, denied = call(server, "slate_sync")
    assert denied
    agentcfg.set_access(repo, agentcfg.FULL)  # user flips the toggle mid-session
    _, denied = call(server, "slate_sync")
    assert not denied


def test_slate_read_returns_ordered_docs_with_contents(repo: Path) -> None:
    init_layer(repo)
    payload, is_error = call(SlateMCPServer(repo), "slate_read")
    assert not is_error
    docs = payload["read_in_order"]
    assert docs[0]["path"] == "AGENTS.md"
    assert all(d["status"] == "fresh" for d in docs)
    assert all(isinstance(d["score"], float) for d in docs)
    assert "# Module map" in next(d for d in docs if d["doc"] == "modules")["contents"]


def test_slate_status_flags_stale_after_change(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    payload, is_error = call(SlateMCPServer(repo), "slate_status")
    assert not is_error
    by_doc = {d["doc"]: d for d in payload}
    assert by_doc["modules"]["status"] == "stale"
    assert "demo/extra.py" in by_doc["modules"]["changed_watched"]


def test_status_json_is_backward_compatible_and_adds_claims(repo: Path) -> None:
    # The VS Code extension + PR bot parse these keys — additive only.
    init_layer(repo)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    payload, _ = call(SlateMCPServer(repo), "slate_status")
    modules = next(d for d in payload if d["doc"] == "modules")
    for key in ("doc", "path", "status", "reason", "changed_watched", "content_verified"):
        assert key in modules  # old contract intact
    assert isinstance(modules["claims"], list)  # new field
    stale_gen = [c for c in modules["claims"] if c["status"] == "stale"]
    assert stale_gen and {"text", "section", "kind", "status", "refs", "risk"} <= set(stale_gen[0])


def test_verify_and_diff_json_carry_claim_breakdown(repo: Path) -> None:
    init_layer(repo)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    verify_payload, _ = call(SlateMCPServer(repo), "slate_verify")
    modules_v = next(d for d in verify_payload if d["doc"] == "modules")
    assert "score" in modules_v and "missing_paths" in modules_v  # old keys
    assert modules_v["total_claims"] >= modules_v["suspect_claims"] >= 1  # new keys
    diff_payload, _ = call(SlateMCPServer(repo), "slate_diff")
    modules_d = next(d for d in diff_payload if d["doc"] == "modules")
    assert "watched_changes" in modules_d and "broken_claims" in modules_d  # old keys
    assert isinstance(modules_d["suspect_claims"], list)  # new key


def test_slate_sync_via_mcp_clears_staleness(repo: Path) -> None:
    init_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    (repo / "demo" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "change")
    server = SlateMCPServer(repo)
    payload, is_error = call(server, "slate_sync")
    assert not is_error
    assert ".slate/modules.md" in payload["synced"]
    status, _ = call(server, "slate_status")
    assert all(d["status"] == "fresh" for d in status)


def test_update_focus_rewrites_section_and_marks(repo: Path) -> None:
    init_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    payload, is_error = call(
        SlateMCPServer(repo), "slate_update_focus",
        {"current_focus": "Building the widget parser.", "landmines": "Do not touch legacy.py."},
    )
    assert not is_error
    text = (repo / ".slate" / "read-next.md").read_text(encoding="utf-8")
    assert "Building the widget parser." in text
    assert "Do not touch legacy.py." in text
    assert "_Nothing in flight._" not in text
    status, _ = call(SlateMCPServer(repo), "slate_status")
    assert next(d for d in status if d["doc"] == "read-next")["status"] == "fresh"


def test_append_decision(repo: Path) -> None:
    init_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    payload, is_error = call(
        SlateMCPServer(repo), "slate_append_decision",
        {"decision": "Use sqlite", "rationale": "Zero ops", "trade_off": "Single writer"},
    )
    assert not is_error
    text = (repo / ".slate" / "decisions.md").read_text(encoding="utf-8")
    assert "Decision: Use sqlite" in text
    assert "Trade-off: Single writer" in text
    # template stays intact (append-only)
    assert "Date: YYYY-MM-DD" in text


def test_missing_layer_is_tool_error_not_crash(repo: Path) -> None:
    payload, is_error = call(SlateMCPServer(repo), "slate_read")
    assert is_error
    assert "slate init" in payload["text"]


def test_unknown_method_and_tool(repo: Path) -> None:
    server = SlateMCPServer(repo)
    resp = server.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
    assert resp["error"]["code"] == -32601
    payload, is_error = call(server, "bogus_tool")
    assert is_error


def test_stdio_loop_round_trip(repo: Path) -> None:
    init_layer(repo)
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + "not json\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
    )
    stdout = io.StringIO()
    assert serve(repo, stdin=stdin, stdout=stdout) == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["id"] == 1
    assert responses[1]["error"]["code"] == -32700  # the bad line
    assert any(t["name"] == "slate_read" for t in responses[2]["result"]["tools"])


def test_replace_section_appends_when_heading_missing() -> None:
    body = "# Doc\n\nsome text\n"
    out = replace_section(body, "## Current focus", "new stuff")
    assert "## Current focus" in out and "new stuff" in out
    assert "some text" in out


def test_replace_section_preserves_following_sections() -> None:
    body = "# Doc\n\n## Current focus\n\nold\n\n## Landmines\n\nkeep me\n"
    out = replace_section(body, "## Current focus", "new")
    assert "old" not in out
    assert "new" in out
    assert "keep me" in out


# --------------------------------------------------------------------------
# repair tools (Phase 3)


def suspect_layer(repo: Path) -> None:
    """A layer with one hand-written claim the code no longer vouches for."""
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text(encoding="utf-8") + "\n`engine.run` returns 42.\n")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n", encoding="utf-8")
    commit_all(repo, "change run")


def enable_repair(repo: Path) -> None:
    agentcfg.set_access(repo, agentcfg.FULL)
    agentcfg.set_repair(repo, agentcfg.REPAIR_ON)


def test_repair_tasks_is_a_read_tool(repo: Path) -> None:
    suspect_layer(repo)
    tools = list_tools(SlateMCPServer(repo))  # default access: read
    assert "slate_repair_tasks" in tools
    payload, is_error = call(SlateMCPServer(repo), "slate_repair_tasks")
    assert not is_error
    assert any("engine.run" in t["text"] for t in payload["tasks"])


def test_repair_apply_is_hidden_without_both_switches(repo: Path) -> None:
    suspect_layer(repo)
    assert "slate_repair_apply" not in list_tools(SlateMCPServer(repo))
    agentcfg.set_access(repo, agentcfg.FULL)  # full access alone is not enough
    assert "slate_repair_apply" not in list_tools(SlateMCPServer(repo))
    agentcfg.set_repair(repo, agentcfg.REPAIR_ON)
    assert "slate_repair_apply" in list_tools(SlateMCPServer(repo))


def test_repair_apply_is_denied_when_repair_is_off(repo: Path) -> None:
    suspect_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_repair_apply", {
        "doc": "read-next", "target": "`engine.run` returns 42.",
        "replacement": "`engine.run` returns 43.",
    })
    assert is_error and "repair is off" in payload["text"]
    assert "`engine.run` returns 42." in (repo / ".slate" / "read-next.md").read_text(encoding="utf-8")


def test_an_honest_repair_is_written(repo: Path) -> None:
    suspect_layer(repo)
    enable_repair(repo)
    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_repair_apply", {
        "doc": "read-next", "target": "`engine.run` returns 42.",
        "replacement": "`engine.run` returns 43.",
    })
    assert not is_error and payload["outcome"] == "repaired"
    body = (repo / ".slate" / "read-next.md").read_text(encoding="utf-8")
    assert "`engine.run` returns 43." in body and "returns 42." not in body


def test_a_repair_that_strips_refs_is_refused_and_writes_nothing(repo: Path) -> None:
    # The false-`fresh` the repair loop could manufacture for itself.
    suspect_layer(repo)
    enable_repair(repo)
    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_repair_apply", {
        "doc": "read-next", "target": "`engine.run` returns 42.",
        "replacement": "The engine returns something sensible.",
    })
    assert is_error and payload["outcome"] == "rejected"
    assert any("never be checked again" in r for r in payload["reasons"])
    assert "`engine.run` returns 42." in (repo / ".slate" / "read-next.md").read_text(encoding="utf-8")


def test_a_repair_does_not_re_anchor_the_doc(repo: Path) -> None:
    """Freshness cannot score a repair — a repair is newer prose by definition,
    so re-stamping would be Slate vouching for text it never checked."""
    suspect_layer(repo)
    enable_repair(repo)
    before = context.load(repo, context.spec_by_name("read-next")).synced_commit
    call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_repair_apply", {
        "doc": "read-next", "target": "`engine.run` returns 42.",
        "replacement": "`engine.run` returns 43.",
    })
    after = context.load(repo, context.spec_by_name("read-next")).synced_commit
    assert after == before


def test_repair_apply_on_a_missing_target_writes_nothing(repo: Path) -> None:
    suspect_layer(repo)
    enable_repair(repo)
    original = (repo / ".slate" / "read-next.md").read_text(encoding="utf-8")
    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_repair_apply", {
        "doc": "read-next", "target": "`engine.run` returns 7.",
        "replacement": "`engine.run` returns 43.",
    })
    assert is_error and payload["outcome"] == "rejected"
    assert (repo / ".slate" / "read-next.md").read_text(encoding="utf-8") == original


def seed_focus_claim(repo: Path) -> Path:
    """An anchored layer whose *Current focus* section carries one claim.

    It has to sit inside that section: `slate_update_focus` replaces the focus
    and nothing else, so a claim parked below Landmines would survive the
    rewrite and the guard would never be exercised.
    """
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    body = read_next.read_text(encoding="utf-8")
    head, marker, tail = body.partition("## Current focus")
    read_next.write_text(f"{head}{marker}\n\n`engine.run` returns 42.\n{tail}", encoding="utf-8")
    commit_all(repo, "describe run")
    agentcfg.set_access(repo, agentcfg.FULL)
    call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_mark", {"docs": ["read-next"]})
    commit_all(repo, "anchor")
    return read_next


def test_slate_mark_refuses_to_retire_a_claim(repo: Path) -> None:
    """The agent gets no `--allow-claim-loss`.

    A human can decide prose is obsolete and say so on the command line. An
    agent that just deleted a claim and is now attesting the doc is accurate is
    the exact sequence the guard exists for, and nothing here can tell the two
    apart.
    """
    init_layer(repo)
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text(encoding="utf-8") + "\n`engine.run` returns 42.\n")
    commit_all(repo, "describe run")
    agentcfg.set_access(repo, agentcfg.FULL)
    call(SlateMCPServer(repo, access=agentcfg.FULL), "slate_mark", {"docs": ["read-next"]})
    commit_all(repo, "anchor")

    read_next.write_text(read_next.read_text(encoding="utf-8").replace(
        "`engine.run` returns 42.", "The engine is fine."))
    before = context.load(repo, context.spec_by_name("read-next")).synced_commit

    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL),
                             "slate_mark", {"docs": ["read-next"]})
    assert is_error and payload["marked"] == []
    assert "engine.run" in json.dumps(payload["refused"])
    # and the anchor did not move
    assert context.load(repo, context.spec_by_name("read-next")).synced_commit == before


def test_update_focus_refuses_to_drop_the_claims_it_replaces(repo: Path) -> None:
    # Measured doing exactly this in the E3 sweep: rewrite the whole focus
    # section, re-anchor in the same call, and the claims the old focus made
    # are retired with nothing having checked them.
    read_next = seed_focus_claim(repo)

    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL),
                             "slate_update_focus", {"current_focus": "All done here."})
    assert is_error and payload["updated"] is None
    assert "`engine.run` returns 42." in read_next.read_text(encoding="utf-8")


def test_update_focus_still_works_when_it_carries_the_claims_over(repo: Path) -> None:
    seed_focus_claim(repo)

    payload, is_error = call(SlateMCPServer(repo, access=agentcfg.FULL),
                             "slate_update_focus",
                             {"current_focus": "`engine.run` returns 43 now."})
    assert not is_error and payload["updated"]
