"""Freshness delivered as a hook, not as an offer.

The measured failure this fixes: across 25 real headless sessions the agent
made 0 calls to any `slate_*` tool in 320 tool calls, despite the MCP server
being connected and AGENTS.md instructing it to check freshness first
(`benchmarks/agentbench/RESULTS.md`). A signal the model must opt into is a
signal the model skips.

Two properties matter more than any rendering detail here, and both are the
kind that fail silently in production:

1. **The hook never breaks a session.** Any malformed payload, missing
   layer, or internal bug resolves to silence and exit 0.
2. **The hook never claims `fresh` for something it did not verify.** Silence
   on failure, never a cheerful default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slate import claudehook, context, freshness, generator, scanner

from .conftest import commit_all


@pytest.fixture
def layered(repo: Path) -> Path:
    """A repo with a generated, all-fresh context layer."""
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")
    return repo


def payload(**kwargs) -> dict:
    return kwargs


def pre_tool(repo: Path, rel: str, tool: str = "Edit") -> dict:
    return payload(
        hook_event_name="PreToolUse",
        tool_name=tool,
        tool_input={"file_path": str(repo / rel)},
    )


def context_text(output: dict | None) -> str:
    assert output is not None
    return output["hookSpecificOutput"]["additionalContext"]


# --- never break the session ------------------------------------------------

@pytest.mark.parametrize("stdin_text", [
    "",
    "not json at all",
    "[]",                      # valid JSON, wrong shape
    "null",
    '{"hook_event_name": "SessionStart"',   # truncated
    '{"no_event": true}',
])
def test_malformed_input_is_silent_not_fatal(layered: Path, stdin_text: str) -> None:
    assert claudehook.run(layered, stdin_text) is None


def test_no_context_layer_is_silent(repo: Path) -> None:
    # A repo that never ran `slate init` must not get an error injected into
    # every session; slate simply has nothing to say.
    out = claudehook.run(repo, json.dumps(payload(hook_event_name="SessionStart")))
    assert out is None


def test_internal_failure_is_silent(layered: Path, monkeypatch) -> None:
    """Even a bug in the freshness engine must not surface as a broken hook."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(freshness, "evaluate_all", boom)
    assert claudehook.run(layered, json.dumps(payload(hook_event_name="SessionStart"))) is None


def test_unknown_event_is_ignored(layered: Path) -> None:
    # Not `Stop` any more — that became a handled event in Phase 3, and this
    # assertion would have kept passing for the wrong reason (repair is off by
    # default, so Stop is silent anyway).
    assert claudehook.build_output(layered, payload(hook_event_name="PreCompact")) is None
    assert claudehook.build_output(layered, payload(hook_event_name="SessionEnd")) is None


# --- SessionStart -----------------------------------------------------------

def test_session_start_reports_all_fresh(layered: Path) -> None:
    text = context_text(claudehook.build_output(
        layered, payload(hook_event_name="SessionStart")))
    assert "fresh" in text
    # The positive half of the signal: an agent that only hears from Slate on
    # failure treats the docs as unqualified the rest of the time.
    assert "NOT fresh" not in text


def test_session_start_names_the_stale_doc(layered: Path) -> None:
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    text = context_text(claudehook.build_output(
        layered, payload(hook_event_name="SessionStart")))
    assert "NOT fresh" in text
    assert "demo/engine.py" in text or ".slate/architecture.md" in text


def test_session_start_never_vouches_for_a_stale_doc(layered: Path) -> None:
    """The invariant that would destroy the product: telling the agent a doc
    is safe when its watched code has moved."""
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    reports = freshness.evaluate_all(layered)
    stale = [r.rel_path for r in reports if r.status != context.FRESH]
    assert stale, "fixture should have produced a non-fresh doc"

    text = context_text(claudehook.build_output(
        layered, payload(hook_event_name="SessionStart")))
    safe_line = next(
        (ln for ln in text.splitlines() if "safe to rely on" in ln), ""
    )
    for path in stale:
        assert path not in safe_line


# --- PreToolUse -------------------------------------------------------------

def test_pre_tool_use_is_silent_when_everything_is_fresh(layered: Path) -> None:
    assert claudehook.build_output(layered, pre_tool(layered, "demo/engine.py")) is None


def test_pre_tool_use_warns_on_a_covered_file(layered: Path) -> None:
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    text = context_text(claudehook.build_output(layered, pre_tool(layered, "demo/engine.py")))
    assert "demo/engine.py" in text
    assert "not fresh" in text


def test_pre_tool_use_is_silent_on_an_uncovered_file(layered: Path) -> None:
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    # README is not under any doc's watch globs, so there is nothing to warn
    # about even though the layer as a whole is stale. Firing here would make
    # the warning a banner, and banners get skimmed.
    assert claudehook.build_output(layered, pre_tool(layered, "README.md")) is None


def test_pre_tool_use_ignores_non_file_tools(layered: Path) -> None:
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    out = claudehook.build_output(layered, payload(
        hook_event_name="PreToolUse",
        tool_name="Bash",
        tool_input={"command": "cat demo/engine.py"},
    ))
    assert out is None


def test_pre_tool_use_ignores_paths_outside_the_repo(layered: Path) -> None:
    out = claudehook.build_output(layered, payload(
        hook_event_name="PreToolUse",
        tool_name="Read",
        tool_input={"file_path": "/etc/hosts"},
    ))
    assert out is None


def test_pre_tool_use_is_silent_on_the_context_layer_itself(layered: Path) -> None:
    """Editing a stale doc is the agent *healing* it — warning would be noise
    at exactly the moment the agent is doing the right thing."""
    (layered / "demo" / "engine.py").write_text("def run():\n    return 99\n", encoding="utf-8")
    commit_all(layered, "change watched code")

    for rel in sorted(context.CONTEXT_DOC_PATHS):
        assert claudehook.build_output(layered, pre_tool(layered, rel)) is None


def test_human_owned_docs_never_match_a_file(layered: Path) -> None:
    """Human docs carry no watches; an empty watch list must match nothing.

    If `any_match([], path)` ever became "matches everything", every file
    touch would warn about read-next.md — and the doc's attestation-based
    freshness says nothing about any particular file anyway.
    """
    reports = freshness.evaluate_all(layered)
    human = [r for r in reports if not r.doc.watches]
    assert human, "fixture should include human-owned docs"
    covering = claudehook._covering(reports, "demo/engine.py")
    assert not any(r.rel_path in {h.rel_path for h in human} for r in covering)


# --- settings.json wiring ---------------------------------------------------

def settings(repo: Path) -> dict:
    return json.loads(claudehook.settings_path(repo).read_text(encoding="utf-8"))


def test_install_writes_both_events(repo: Path) -> None:
    claudehook.install(repo)
    hooks = settings(repo)["hooks"]
    assert claudehook.SESSION_START in hooks
    assert claudehook.PRE_TOOL_USE in hooks


def test_pre_tool_use_matcher_covers_the_file_tools(repo: Path) -> None:
    claudehook.install(repo)
    group = settings(repo)["hooks"][claudehook.PRE_TOOL_USE][0]
    for tool in claudehook.WATCHED_TOOLS:
        assert tool in group["matcher"]


def test_session_start_matcher_is_empty_so_compaction_is_covered(repo: Path) -> None:
    # An empty matcher fires for every source, including `compact` — which is
    # precisely when a summarized layer loses its freshness qualifiers.
    claudehook.install(repo)
    group = settings(repo)["hooks"][claudehook.SESSION_START][0]
    assert group["matcher"] == ""


def test_install_is_idempotent(repo: Path) -> None:
    claudehook.install(repo)
    claudehook.install(repo)
    hooks = settings(repo)["hooks"]
    for event in (claudehook.SESSION_START, claudehook.PRE_TOOL_USE):
        assert len(hooks[event]) == 1, "repeated install stacked duplicate entries"


def test_install_preserves_other_tools_hooks(repo: Path) -> None:
    path = claudehook.settings_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool"}]}
            ]
        },
    }), encoding="utf-8")
    claudehook.install(repo)

    config = settings(repo)
    assert config["permissions"] == {"allow": ["Bash(ls:*)"]}
    commands = [
        h["command"]
        for g in config["hooks"]["PreToolUse"] for h in g["hooks"]
    ]
    assert "other-tool" in commands
    assert claudehook.HOOK_COMMAND in commands


def test_uninstall_removes_only_ours(repo: Path) -> None:
    path = claudehook.settings_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool"}]}
            ]
        }
    }), encoding="utf-8")
    claudehook.install(repo)
    assert claudehook.uninstall(repo) is True

    config = settings(repo)
    commands = [
        h["command"]
        for g in config.get("hooks", {}).get("PreToolUse", []) for h in g["hooks"]
    ]
    assert commands == ["other-tool"]


def test_uninstall_reports_when_nothing_installed(repo: Path) -> None:
    assert claudehook.uninstall(repo) is False


def test_installed_events_reflects_state(repo: Path) -> None:
    assert claudehook.installed_events(repo) == []
    claudehook.install(repo)
    assert set(claudehook.installed_events(repo)) == {
        claudehook.SESSION_START, claudehook.PRE_TOOL_USE, claudehook.STOP
    }


def test_malformed_settings_file_is_reported_not_clobbered(repo: Path) -> None:
    path = claudehook.settings_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(claudehook.HookConfigError):
        claudehook.install(repo)
    assert path.read_text(encoding="utf-8") == "{ this is not json"


def test_installed_events_survives_a_malformed_settings_file(repo: Path) -> None:
    # Status must never raise — it is called from `slate agent status`.
    path = claudehook.settings_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    assert claudehook.installed_events(repo) == []


# --- the emitted payload is what Claude Code expects ------------------------

def test_output_shape_matches_the_hook_contract(layered: Path) -> None:
    raw = claudehook.run(layered, json.dumps(payload(hook_event_name="SessionStart")))
    assert raw is not None
    parsed = json.loads(raw)
    specific = parsed["hookSpecificOutput"]
    assert specific["hookEventName"] == claudehook.SESSION_START
    assert isinstance(specific["additionalContext"], str)
    assert specific["additionalContext"].strip()


# --- co-change injection ----------------------------------------------------
# The revision-3 sweep put `src/flask/app.py <-> src/flask/sessions.py` in the
# rendered layer — the exact coupling every trial missed — and every trial
# missed it anyway, whether or not it opened the doc. These tests pin the
# active form: the same fact, delivered when the agent edits the file.

def edit(repo: Path, rel: str, session: str = "s1", tool: str = "Edit") -> dict:
    return payload(
        hook_event_name="PreToolUse",
        tool_name=tool,
        session_id=session,
        tool_input={"file_path": str(repo / rel)},
    )


@pytest.fixture
def coupled(layered: Path, monkeypatch) -> Path:
    """A repo where engine.py and cli.py demonstrably move together.

    Opts in explicitly: co-change is off by default on the evidence, so a
    test that did not set this would pass for the wrong reason.
    """
    from slate import cochange
    monkeypatch.setenv(cochange.ENABLED_ENV, "1")
    for i in range(5):
        (layered / "demo" / "engine.py").write_text(f"def run():\n    return {i}\n", encoding="utf-8")
        (layered / "demo" / "cli.py").write_text(f"def main():\n    return {i}\n", encoding="utf-8")
        commit_all(layered, f"paired-{i}")
    return layered


def test_editing_a_coupled_file_names_its_partner(coupled: Path) -> None:
    text = context_text(claudehook.build_output(coupled, edit(coupled, "demo/engine.py")))
    assert "demo/cli.py" in text


def test_cochange_is_off_without_the_opt_in(layered: Path, monkeypatch) -> None:
    from slate import cochange
    monkeypatch.delenv(cochange.ENABLED_ENV, raising=False)
    for i in range(5):
        (layered / "demo" / "engine.py").write_text(f"def run():\n    return {i}\n", encoding="utf-8")
        (layered / "demo" / "cli.py").write_text(f"def main():\n    return {i}\n", encoding="utf-8")
        commit_all(layered, f"paired-{i}")
    out = claudehook.build_output(layered, edit(layered, "demo/engine.py"))
    text = "" if out is None else context_text(out)
    assert "changed together" not in text


def test_reading_does_not_trigger_cochange(coupled: Path) -> None:
    out = claudehook.build_output(coupled, edit(coupled, "demo/engine.py", tool="Read"))
    text = "" if out is None else context_text(out)
    assert "changed together" not in text


def test_a_pair_is_announced_once_per_session(coupled: Path) -> None:
    """A warning that repeats on every edit is a banner, and banners are the
    failure mode this exists to escape."""
    first = claudehook.build_output(coupled, edit(coupled, "demo/engine.py", "sess-a"))
    assert "demo/cli.py" in context_text(first)

    second = claudehook.build_output(coupled, edit(coupled, "demo/engine.py", "sess-a"))
    text = "" if second is None else context_text(second)
    assert "demo/cli.py" not in text


def test_a_new_session_hears_it_again(coupled: Path) -> None:
    claudehook.build_output(coupled, edit(coupled, "demo/engine.py", "sess-a"))
    again = claudehook.build_output(coupled, edit(coupled, "demo/engine.py", "sess-b"))
    assert "demo/cli.py" in context_text(again)


def test_uncoupled_file_stays_silent(coupled: Path) -> None:
    (coupled / "demo" / "lonely.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(coupled, "lonely")
    out = claudehook.build_output(coupled, edit(coupled, "demo/lonely.py"))
    text = "" if out is None else context_text(out)
    assert "changed together" not in text


def test_editing_the_context_layer_stays_silent(coupled: Path) -> None:
    for rel in sorted(context.CONTEXT_DOC_PATHS):
        out = claudehook.build_output(coupled, edit(coupled, rel))
        text = "" if out is None else context_text(out)
        assert "changed together" not in text


def test_a_missing_session_id_does_not_break_the_hook(coupled: Path) -> None:
    out = claudehook.build_output(coupled, payload(
        hook_event_name="PreToolUse", tool_name="Edit",
        tool_input={"file_path": str(coupled / "demo" / "engine.py")},
    ))
    assert "demo/cli.py" in context_text(out)


def test_cochange_failure_does_not_break_the_hook(coupled: Path, monkeypatch) -> None:
    from slate import cochange

    def boom(*_a, **_k):
        raise RuntimeError("history exploded")

    monkeypatch.setattr(cochange, "partners", boom)
    raw = claudehook.run(coupled, json.dumps(edit(coupled, "demo/engine.py")))
    assert raw is None or "changed together" not in raw


# --------------------------------------------------------------------------
# Stop: the session-end repair prompt (Phase 3)
#
# It rides `Stop` rather than `SessionEnd` because `SessionEnd` cannot inject
# anything — no decision control, no `additionalContext`, it fires after the
# session is over. `Stop` fires when the model finishes a turn and continues
# the conversation, which is the only place an end-of-session job can be acted
# on. That continuation is also why the loop guards below are not optional.


def stop(session_id: str = "s1", **kwargs) -> dict:
    return payload(hook_event_name="Stop", session_id=session_id, **kwargs)


@pytest.fixture
def suspect(layered: Path) -> Path:
    """A layer with one hand-written claim the code no longer vouches for."""
    read_next = layered / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text(encoding="utf-8") + "\n`engine.run` returns 42.\n")
    commit_all(layered, "describe run")
    (layered / "demo" / "engine.py").write_text("def run():\n    return 43\n", encoding="utf-8")
    commit_all(layered, "change run")
    return layered


def enable_repair(repo: Path) -> None:
    from slate import agentcfg
    agentcfg.set_access(repo, agentcfg.FULL)
    agentcfg.set_repair(repo, agentcfg.REPAIR_ON)


def test_stop_is_silent_by_default(suspect: Path) -> None:
    # There is a real repair task here; the switch is what keeps it quiet.
    assert claudehook.build_output(suspect, stop()) is None


def test_stop_needs_both_switches(suspect: Path) -> None:
    from slate import agentcfg
    agentcfg.set_repair(suspect, agentcfg.REPAIR_ON)  # but access is still read
    assert claudehook.build_output(suspect, stop()) is None
    agentcfg.set_access(suspect, agentcfg.FULL)
    assert claudehook.build_output(suspect, stop()) is not None


def test_stop_names_the_suspect_claim(suspect: Path) -> None:
    enable_repair(suspect)
    out = claudehook.build_output(suspect, stop())
    specific = out["hookSpecificOutput"]
    assert specific["hookEventName"] == claudehook.STOP
    text = specific["additionalContext"]
    assert "engine.run" in text
    # It must offer, not command: a bare imperative injected by a hook reads as
    # a prompt-injection attempt, and a canary against a real session had one
    # identified and refused.
    assert "correct outcome" in text


def test_stop_stays_silent_when_the_layer_is_clean(layered: Path) -> None:
    enable_repair(layered)
    assert claudehook.build_output(layered, stop()) is None


def test_stop_hook_active_ends_the_loop(suspect: Path) -> None:
    # `additionalContext` on Stop continues the conversation, so a hook that
    # speaks unconditionally never lets the session end.
    enable_repair(suspect)
    assert claudehook.build_output(suspect, stop(stop_hook_active=True)) is None


def test_stop_announces_once_per_session(suspect: Path) -> None:
    # The second brake, independent of the client: if a future Claude Code
    # drops `stop_hook_active`, this still bounds it to one announcement.
    enable_repair(suspect)
    assert claudehook.build_output(suspect, stop("abc")) is not None
    assert claudehook.build_output(suspect, stop("abc")) is None
    assert claudehook.build_output(suspect, stop("def")) is not None


def test_stop_never_blocks(suspect: Path) -> None:
    # A hook that blocks the stop is a hook that can stop a session ending,
    # which is the landmine this module is built around.
    enable_repair(suspect)
    out = claudehook.build_output(suspect, stop())
    assert "decision" not in out
    assert set(out) == {"hookSpecificOutput"}


def test_stop_failure_is_silence(suspect: Path) -> None:
    enable_repair(suspect)
    assert claudehook.run(suspect, '{"hook_event_name": "Stop"') is None
    assert claudehook.run(suspect, "not json at all") is None
