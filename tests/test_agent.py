"""Agent wiring: access ceiling persistence and MCP client registration."""

import json
from pathlib import Path

from slate import agentcfg
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
    agentcfg.access_path(repo).write_text("yolo\n")
    assert agentcfg.get_access(repo) == "read"


def test_enable_writes_client_config(repo: Path) -> None:
    rel = agentcfg.enable_client(repo, "claude")
    assert rel == ".mcp.json"
    config = json.loads((repo / ".mcp.json").read_text())
    assert config["mcpServers"]["slate"] == {"command": "slate", "args": ["mcp"]}
    assert agentcfg.enabled_clients(repo) == ["claude"]


def test_enable_merges_with_existing_config(repo: Path) -> None:
    (repo / ".mcp.json").write_text(json.dumps({
        "mcpServers": {"other": {"command": "other-tool", "args": []}}
    }))
    agentcfg.enable_client(repo, "claude")
    config = json.loads((repo / ".mcp.json").read_text())
    assert "other" in config["mcpServers"]  # never clobber someone else's server
    assert "slate" in config["mcpServers"]


def test_enable_rejects_broken_config(repo: Path) -> None:
    (repo / ".mcp.json").write_text("{not json")
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
    agentcfg.repair_path(repo).write_text("yes please\n")
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
