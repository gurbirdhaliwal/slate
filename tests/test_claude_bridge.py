"""The Claude Code instruction bridge.

Claude Code loads `CLAUDE.md` and never `AGENTS.md` — it treats AGENTS.md as a
foreign format and only reads it when importing from Codex. Slate hangs its
whole context layer off AGENTS.md, so before this bridge existed a Slate repo
shipped Claude Code nothing at all, and did it silently: the MCP server still
connected, the docs still sat in the tree, and none of it reached the model.

Measured, not assumed: a canary instruction placed in AGENTS.md was ignored in
3/3 headless runs, while the same text in CLAUDE.md was followed every time.
"""

from __future__ import annotations

from pathlib import Path

from slate import agentcfg, context

from .conftest import commit_all


def bridge(repo: Path) -> Path:
    return repo / context.CLAUDE_BRIDGE


def test_bridge_is_written_when_absent(repo: Path) -> None:
    assert agentcfg.bridge_claude(repo) == agentcfg.WROTE
    assert agentcfg.BRIDGE_IMPORT in bridge(repo).read_text(encoding="utf-8")


def test_bridge_import_is_on_its_own_line(repo: Path) -> None:
    # Claude Code expands `@path` imports found in the body; a line that merely
    # mentions the path in prose would not load anything.
    agentcfg.bridge_claude(repo)
    lines = [ln.strip() for ln in bridge(repo).read_text(encoding="utf-8").splitlines()]
    assert agentcfg.BRIDGE_IMPORT in lines


def test_bridge_is_idempotent(repo: Path) -> None:
    agentcfg.bridge_claude(repo)
    before = bridge(repo).read_text(encoding="utf-8")
    assert agentcfg.bridge_claude(repo) == agentcfg.ALREADY
    assert bridge(repo).read_text(encoding="utf-8") == before


def test_existing_claude_md_is_never_clobbered(repo: Path) -> None:
    # A user's own instructions outrank ours. Overwriting them to install a
    # pointer would be a worse bug than the one being fixed.
    bridge(repo).write_text("# My rules\n\nAlways use tabs.\n", encoding="utf-8")
    assert agentcfg.bridge_claude(repo) == agentcfg.MANUAL
    assert "Always use tabs." in bridge(repo).read_text(encoding="utf-8")
    assert agentcfg.BRIDGE_IMPORT not in bridge(repo).read_text(encoding="utf-8")


def test_user_file_that_already_imports_counts_as_wired(repo: Path) -> None:
    bridge(repo).write_text(f"{agentcfg.BRIDGE_IMPORT}\n\n## Extra\n\nBe terse.\n", encoding="utf-8")
    assert agentcfg.bridge_claude(repo) == agentcfg.ALREADY


def test_import_inside_a_code_fence_does_not_count(repo: Path) -> None:
    # Claude Code skips fenced blocks when parsing imports, so a documented
    # example is not a live import. Reporting it as wired would leave the user
    # believing the layer loads when it does not.
    bridge(repo).write_text(
        f"# Docs\n\nTo wire this up, add:\n\n```\n{agentcfg.BRIDGE_IMPORT}\n```\n"
    , encoding="utf-8")
    assert agentcfg.bridge_claude(repo) == agentcfg.MANUAL


def test_bridge_does_not_invalidate_the_layer(repo: Path) -> None:
    # `**` is the module map's watch pattern on a repo with no source dirs, so
    # an unexcluded bridge file would stale a doc the moment Slate wrote it.
    assert context.CLAUDE_BRIDGE in context.CONTEXT_DOC_PATHS


def test_init_writes_the_bridge(repo: Path) -> None:
    from slate import cli

    assert cli.main(["-C", str(repo), "init"]) == 0
    assert agentcfg.BRIDGE_IMPORT in bridge(repo).read_text(encoding="utf-8")


def test_init_warns_instead_of_overwriting(repo: Path, capsys) -> None:
    from slate import cli

    bridge(repo).write_text("# Mine\n", encoding="utf-8")
    assert cli.main(["-C", str(repo), "init"]) == 0
    out = capsys.readouterr().out
    assert agentcfg.BRIDGE_IMPORT in out  # told the user what to add
    assert bridge(repo).read_text(encoding="utf-8") == "# Mine\n"


def test_layer_stays_fresh_after_the_bridge_lands(repo: Path) -> None:
    # End to end: init writes AGENTS.md and CLAUDE.md, commit them, and nothing
    # is reported stale purely because the bridge appeared.
    from slate import cli, freshness

    cli.main(["-C", str(repo), "init"])
    commit_all(repo, "context layer")
    statuses = {r.doc.spec.name: r.status for r in freshness.evaluate_all(repo)}
    assert set(statuses.values()) == {context.FRESH}, statuses


def test_sync_backfills_the_bridge_for_older_repos(repo: Path) -> None:
    # A repo initialised before the bridge existed has already run `init` and
    # would never see it otherwise — sync is the command those users do run.
    from slate import cli

    cli.main(["-C", str(repo), "init"])
    bridge(repo).unlink()
    commit_all(repo, "layer without bridge")

    assert cli.main(["-C", str(repo), "sync"]) == 0
    assert agentcfg.BRIDGE_IMPORT in bridge(repo).read_text(encoding="utf-8")


def test_sync_that_creates_the_bridge_leaves_the_layer_settled(repo: Path) -> None:
    # The bridge is a new file, and the scanned facts include a file count. If
    # it lands after the scan, sync writes facts describing a tree that is
    # already one file out of date, and the next sync silently rewrites them.
    from slate import cli, context, generator, scanner

    cli.main(["-C", str(repo), "init"])
    bridge(repo).unlink()
    commit_all(repo, "layer without bridge")
    cli.main(["-C", str(repo), "sync"])

    arch = context.spec_by_name("architecture")
    after_sync = arch.path(repo).read_text(encoding="utf-8")
    fresh_block = generator.auto_content(arch, scanner.scan(repo))
    assert fresh_block in after_sync, "a second sync would rewrite the facts"
