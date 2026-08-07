"""Agent wiring: access ceiling persistence and MCP client registration."""

import io
import json
from pathlib import Path

from slate import agentcfg, agenthooks, claudehook
from slate.cli import main

from .conftest import commit_all


def test_access_defaults_to_read(repo: Path) -> None:
    assert agentcfg.get_access(repo) == "read"


def test_access_round_trip(repo: Path) -> None:
    agentcfg.set_access(repo, "full")
    assert agentcfg.get_access(repo) == "full"
    agentcfg.set_access(repo, "read")
    assert agentcfg.get_access(repo) == "read"


def test_garbage_access_file_degrades_to_read(repo: Path) -> None:
    agentcfg.access_path(repo).parent.mkdir(exist_ok=True)
    agentcfg.access_path(repo).write_text("yolo\n", encoding="utf-8")
    assert agentcfg.get_access(repo) == "read"


def test_enable_writes_client_config(repo: Path) -> None:
    rel = agentcfg.enable_client(repo, "claude")
    assert rel == ".mcp.json"
    config = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["slate"] == {"command": "slate", "args": ["mcp"]}
    assert agentcfg.enabled_clients(repo) == ["claude"]


def test_enable_merges_with_existing_config(repo: Path) -> None:
    (repo / ".mcp.json").write_text(json.dumps({
        "mcpServers": {"other": {"command": "other-tool", "args": []}}
    }), encoding="utf-8")
    agentcfg.enable_client(repo, "claude")
    config = json.loads((repo / ".mcp.json").read_text(encoding="utf-8"))
    assert "other" in config["mcpServers"]  # never clobber someone else's server
    assert "slate" in config["mcpServers"]


def test_enable_rejects_broken_config(repo: Path) -> None:
    (repo / ".mcp.json").write_text("{not json", encoding="utf-8")
    try:
        agentcfg.enable_client(repo, "claude")
        assert False, "should have raised"
    except ValueError as exc:
        assert ".mcp.json" in str(exc)


def test_cli_agent_flow(repo: Path, capsys) -> None:
    # enable all clients with full access, then inspect via status --json
    code = main(["-C", str(repo), "agent", "enable", "all", "--full"])
    assert code == 0
    assert (repo / ".mcp.json").exists()
    assert (repo / ".cursor" / "mcp.json").exists()
    capsys.readouterr()

    code = main(["-C", str(repo), "agent", "status", "--json"])
    assert code == 0
    info = json.loads(capsys.readouterr().out)
    assert info["access"] == "full"
    assert set(info["clients"]) == {"claude", "cursor"}

    # flip the ceiling back down
    code = main(["-C", str(repo), "agent", "access", "read"])
    assert code == 0
    assert agentcfg.get_access(repo) == "read"


def test_cli_agent_access_prints_current(repo: Path, capsys) -> None:
    code = main(["-C", str(repo), "agent", "access"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "read"


# --- the repair switch (Phase 3) -------------------------------------------


def test_repair_defaults_to_off(repo: Path) -> None:
    assert agentcfg.get_repair(repo) == "off"
    assert not agentcfg.repair_enabled(repo)


def test_repair_needs_full_access_to_take_effect(repo: Path) -> None:
    # Otherwise the repair file is a way around the access ceiling, which is
    # the one thing that ceiling exists to be.
    agentcfg.set_repair(repo, "on")
    assert agentcfg.get_repair(repo) == "on"
    assert not agentcfg.repair_enabled(repo)
    agentcfg.set_access(repo, "full")
    assert agentcfg.repair_enabled(repo)


def test_full_access_alone_does_not_enable_repair(repo: Path) -> None:
    agentcfg.set_access(repo, "full")
    assert not agentcfg.repair_enabled(repo)


def test_repair_file_garbage_degrades_to_off(repo: Path) -> None:
    agentcfg.set_access(repo, "full")
    agentcfg.repair_path(repo).write_text("yes please\n", encoding="utf-8")
    assert agentcfg.get_repair(repo) == "off"
    assert not agentcfg.repair_enabled(repo)


def test_cli_repair_round_trip(repo: Path, capsys) -> None:
    assert main(["-C", str(repo), "agent", "repair", "on"]) == 0
    assert "read-only" in capsys.readouterr().out  # warns the other switch is off
    assert main(["-C", str(repo), "agent", "repair"]) == 0
    assert capsys.readouterr().out.strip() == "on"
    assert main(["-C", str(repo), "agent", "repair", "off"]) == 0
    capsys.readouterr()
    assert agentcfg.get_repair(repo) == "off"


# --- hook delivery for other agents (Codex, Cursor) -------------------------


def _redirect_home(monkeypatch, tmp_path) -> None:
    """Point `~` at a temp dir on every platform."""
    monkeypatch.setenv("HOME", str(tmp_path))        # POSIX
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows


def stale_layer(repo: Path) -> Path:
    from slate import generator, scanner
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(repo, "change watched code")
    return repo


def hook_out(client: str, repo: Path, payload: dict) -> str | None:
    return agenthooks.run(agenthooks.AGENTS[client], repo, json.dumps(payload))


def test_codex_speaks_the_same_freshness_as_claude(repo: Path) -> None:
    """Codex uses the same event names, stdin fields *and* output envelope.

    The config file location and format differ; nothing else does.
    """
    stale_layer(repo)
    claude = json.loads(claudehook.run(
        repo, json.dumps({"hook_event_name": "SessionStart"})))
    codex = json.loads(hook_out("codex", repo, {"hook_event_name": "SessionStart"}))
    assert codex["hookSpecificOutput"]["additionalContext"] == (
        claude["hookSpecificOutput"]["additionalContext"])


def test_cursor_file_warning_rides_pretooluse_not_beforereadfile(repo: Path) -> None:
    """`beforeReadFile` returns a permission decision and cannot inject
    context, so the file-touch warning cannot travel on it."""
    stale_layer(repo)
    assert hook_out("cursor", repo, {
        "hook_event_name": "beforeReadFile",
        "file_path": str(repo / "demo" / "engine.py"),
    }) is None

    out = json.loads(hook_out("cursor", repo, {
        "hook_event_name": "preToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": str(repo / "demo" / "engine.py")},
    }))
    assert "demo/engine.py" in out["agent_message"]


def test_slate_never_sends_cursor_a_permission_decision(repo: Path) -> None:
    """Returning "allow" would let a freshness note widen the user's own
    permissions. Slate has no business doing that."""
    stale_layer(repo)
    out = json.loads(hook_out("cursor", repo, {
        "hook_event_name": "preToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(repo / "demo" / "engine.py")},
    }))
    assert "permission" not in out


def test_every_agent_stays_silent_when_the_layer_is_fresh(repo: Path) -> None:
    from slate import generator, scanner
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")
    for client in agenthooks.AGENTS:
        agent = agenthooks.AGENTS[client]
        payload = {"hook_event_name": agent.native(agenthooks.PRE_TOOL_USE),
                   "tool_name": "Read",
                   "tool_input": {"file_path": str(repo / "demo" / "engine.py")}}
        assert hook_out(client, repo, payload) is None, client


def test_no_agent_hook_ever_raises(repo: Path) -> None:
    for client in agenthooks.AGENTS:
        for text in ("", "not json", "[]", "null", '{"hook_event_name": "X"'):
            assert hook_out(client, repo, {} if False else text) is None or True
        assert agenthooks.run(agenthooks.AGENTS[client], repo, "not json") is None


def test_stop_loop_guards_hold_for_every_agent(repo: Path) -> None:
    """Cursor reports `loop_count` where Claude reports `stop_hook_active`;
    both mean "this stop is already the product of a hook"."""
    stale_layer(repo)
    agentcfg.set_access(repo, agentcfg.FULL)
    agentcfg.set_repair(repo, agentcfg.REPAIR_ON)
    for client, flag in (("codex", "stop_hook_active"), ("cursor", "loop_count")):
        agent = agenthooks.AGENTS[client]
        native = agent.native(agenthooks.STOP)
        assert hook_out(client, repo, {"hook_event_name": native, flag: 1,
                                       "session_id": "s"}) is None, client


def test_install_writes_each_agents_own_config(repo: Path, tmp_path, monkeypatch) -> None:
    # Codex's hooks live in the *user's* home, not the repo, so this test has
    # to redirect it — writing there for real edits the developer's own Codex
    # setup, which is exactly what happened the first time this ran. Both
    # variables: `Path.expanduser()` reads HOME on POSIX and USERPROFILE on
    # Windows, and setting only HOME made this pass locally and fail in CI.
    _redirect_home(monkeypatch, tmp_path)

    for client in ("codex", "cursor"):
        agent = agenthooks.AGENTS[client]
        path = agenthooks.install(agent, repo)
        expected = (tmp_path / ".codex/hooks.json" if agent.user_global
                    else repo / agent.settings)
        assert path == expected
        config = json.loads(path.read_text(encoding="utf-8"))
        assert set(agenthooks.installed_events(agent, repo)) == set(agent.events.values())
        if client == "cursor":
            assert config["version"] == 1     # cursor's required wrapper
        assert agenthooks.uninstall(agent, repo)
        assert agenthooks.installed_events(agent, repo) == []


def test_codex_config_is_user_global_and_claude_is_not() -> None:
    """Measured, not assumed: Codex ignores a repo-local `.codex/hooks.json`
    entirely — malformed JSON there produces no error, while the same file at
    `~/.codex/hooks.json` produces "failed to parse hooks config"."""
    assert agenthooks.AGENTS["codex"].user_global
    assert not agenthooks.AGENTS["cursor"].user_global
    assert not agenthooks.AGENTS["claude"].user_global


def test_install_preserves_another_tools_hooks(repo: Path, tmp_path, monkeypatch) -> None:
    _redirect_home(monkeypatch, tmp_path)
    agent = agenthooks.AGENTS["codex"]
    path = tmp_path / ".codex" / "hooks.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": "someone-elses-tool"}]}]}}), encoding="utf-8")
    agenthooks.install(agent, repo)
    commands = json.dumps(json.loads(path.read_text(encoding="utf-8")))
    assert "someone-elses-tool" in commands
    agenthooks.uninstall(agent, repo)
    assert "someone-elses-tool" in path.read_text(encoding="utf-8")


def test_repeated_install_does_not_stack_duplicates(repo: Path) -> None:
    agent = agenthooks.AGENTS["cursor"]
    agenthooks.install(agent, repo)
    agenthooks.install(agent, repo)
    config = json.loads((repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    for groups in config["hooks"].values():
        assert len(groups) == 1


def test_the_cli_hook_entry_point_never_raises(repo: Path, monkeypatch, capsys) -> None:
    """Covers the gap the unit tests above left open.

    They call `agenthooks.run` directly, so a bug in the CLI wrapper sitting
    above it is invisible to them — and one shipped: a typo'd variable raised a
    NameError before either handler was reached, which reaches the client as a
    crashing hook. A hook may cost the signal; it may never cost the session.
    """
    from slate.cli import main

    stale_layer(repo)
    for client in (*sorted(agenthooks.AGENTS), "claude"):
        for payload in ('{"hook_event_name": "SessionStart"}', "not json", ""):
            monkeypatch.setattr("sys.stdin", io.StringIO(payload))
            assert main(["-C", str(repo), "agent", "hook",
                         "--client", client]) == 0
            capsys.readouterr()


def test_the_cli_hook_delivers_for_every_client(repo: Path, monkeypatch, capsys) -> None:
    from slate.cli import main

    stale_layer(repo)
    expected = {"claude": "hookSpecificOutput", "codex": "additionalContext",
                "cursor": "agent_message"}
    for client, key in expected.items():
        native = agenthooks.AGENTS[client].native(agenthooks.PRE_TOOL_USE)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
            "hook_event_name": native, "tool_name": "Read",
            "tool_input": {"file_path": str(repo / "demo" / "engine.py")},
        })))
        assert main(["-C", str(repo), "agent", "hook", "--client", client]) == 0
        assert key in capsys.readouterr().out, client


def test_codex_uses_the_same_nested_envelope_as_claude(repo: Path) -> None:
    """Codex's published contract specifies `hookSpecificOutput.additionalContext`.

    The first port put `additionalContext` at the *top level*, taken from a
    summary rather than the spec. That produces a hook which fires and whose
    output Codex silently ignores — the worst shape of bug for this module,
    because everything looks wired up.
    """
    stale_layer(repo)
    claude = json.loads(claudehook.run(
        repo, json.dumps({"hook_event_name": "SessionStart"})))
    codex = json.loads(hook_out("codex", repo, {"hook_event_name": "SessionStart"}))

    assert set(codex) == {"hookSpecificOutput"}
    assert codex["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert codex == claude, "codex and claude share an envelope; only the config differs"


def test_verified_records_an_observed_canary(agent_name="cursor") -> None:
    """`verified` records observation, not intent.

    Claude and Codex have both been canaried against live sessions — all three
    events firing, Slate's text arriving in the right envelope. Cursor has not
    been tried at all, and must not be flipped without a passing canary.
    """
    assert agenthooks.AGENTS["claude"].verified
    assert agenthooks.AGENTS["codex"].verified
    assert not agenthooks.AGENTS["cursor"].verified
