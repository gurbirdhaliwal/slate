"""Hook delivery for agents other than Claude Code.

`claudehook` owns the rendering — what a session-start summary says, when a
file-touch warning fires, what an end-of-turn repair prompt looks like. None of
that is Claude-specific; it is Slate deciding what to say. What *is* specific
is the envelope: which lifecycle event fires, where the config lives, and what
JSON shape the client reads back. This module is that envelope, once per agent.

The renderers are imported, never reimplemented. A second copy of "is this doc
fresh" is the failure the whole project is organised against, and a second copy
of "what should we say about it" is the same mistake one layer out.

What the clients actually do, checked against their docs rather than assumed:

  Claude Code   `.claude/settings.json`. Events `SessionStart`, `PreToolUse`,
                `Stop`. Output nests under `hookSpecificOutput`. Canary-verified
                against a real session — see `claudehook`.

  Codex         `.codex/hooks.json`. Same event names, same stdin fields
                (`hook_event_name`, `tool_name`, `tool_input`, `cwd`), and
                `additionalContext` at the top level rather than nested. The
                closest thing to a drop-in of the three.

  Cursor        `.cursor/hooks.json`, `{"version": 1, "hooks": {...}}`, and
                camelCase event names. Two things differ in kind:

                * `beforeReadFile` **cannot inject context**. It returns a
                  permission decision and nothing else, so the file-touch
                  warning cannot ride it. `preToolUse` carries `agent_message`,
                  so that is where it goes.
                * We never send a `permission` field. Returning "allow" would
                  make Slate quietly approve tool calls the user's own settings
                  might have stopped — a freshness note has no business
                  widening anyone's permissions.

**Delivery is verified for Claude Code only, and the Codex canary FAILED.**

Measured 2026-08-05 against `codex-cli 0.137.0`: a repo with the layer stale, a
`.codex/hooks.json` written by `install`, and the hook command tee'd on both
ends produced **zero invocations** — with hook trust bypassed
(`--dangerously-bypass-hook-trust`) and across three config shapes. The binary
plainly implements hooks (it carries `PreToolUse`, `SessionStart`,
`HookHandlerConfig::Command`, `trusted_hash` and a schema of
`event`/`enabled`/`matcher`/`timeout`/`command`), so the feature exists and
Slate is writing the wrong thing, or writing it to the wrong place, or missing
a trust step. The published contract this module was built from describes a
map-of-events shape that this version does not appear to accept.

Cursor has not been tried at all — no CLI available on the machine.

So: the envelope logic below is tested and the rendering is shared and correct,
but **nothing here is known to reach a Codex or Cursor model.** `install` says
so out loud. Do not describe these as supported; describe them as written
against a published contract and not yet observed working. Fixing this needs
the schema for a specific Codex version, and then the same canary re-run — the
canary is the deliverable, not the config file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import claudehook

# Neutral event names. The renderers key off these; each agent maps them to
# whatever it calls the same moment.
SESSION_START = "session_start"
PRE_TOOL_USE = "pre_tool_use"
STOP = "stop"

HOOK_COMMAND = "slate agent hook"


class HookConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class HookAgent:
    name: str
    settings: str                       # repo-relative config path
    events: dict[str, str]              # neutral -> native event name
    envelope: Callable[[str, str], dict]  # (native event, text) -> client JSON
    # Cursor wraps its hook map in {"version": 1, "hooks": {...}}; the others
    # nest under a bare "hooks" key.
    wrapper: dict = field(default_factory=dict)
    # Claude Code matches PreToolUse against a tool-name regex. Codex and
    # Cursor take the event without one.
    matcher: bool = False
    beta: bool = False
    # Has a hook from this adapter been *observed* reaching a live session?
    # Only Claude Code has. Codex was canaried and produced zero invocations;
    # Cursor has not been tried. Anything False here is a config file we
    # believe in, not a delivery path we have seen work.
    verified: bool = False

    def native(self, event: str) -> str | None:
        return self.events.get(event)

    def neutral(self, native_event: str) -> str | None:
        for neutral, name in self.events.items():
            if name == native_event:
                return neutral
        return None


def _claude_envelope(event: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": text}}


def _codex_envelope(_event: str, text: str) -> dict:
    return {"additionalContext": text}


def _cursor_envelope(event: str, text: str) -> dict:
    # No `permission` key, ever — see the module docstring.
    if event == "stop":
        return {"followup_message": text}
    if event == "preToolUse":
        return {"agent_message": text}
    return {"additional_context": text}


AGENTS: dict[str, HookAgent] = {
    "claude": HookAgent(
        name="claude",
        settings=claudehook.SETTINGS_FILE,
        events={SESSION_START: "SessionStart",
                PRE_TOOL_USE: "PreToolUse",
                STOP: "Stop"},
        envelope=_claude_envelope,
        matcher=True,
        verified=True,
    ),
    "codex": HookAgent(
        name="codex",
        settings=".codex/hooks.json",
        events={SESSION_START: "SessionStart",
                PRE_TOOL_USE: "PreToolUse",
                STOP: "Stop"},
        envelope=_codex_envelope,
    ),
    "cursor": HookAgent(
        name="cursor",
        settings=".cursor/hooks.json",
        events={SESSION_START: "sessionStart",
                PRE_TOOL_USE: "preToolUse",
                STOP: "stop"},
        envelope=_cursor_envelope,
        wrapper={"version": 1},
        beta=True,
    ),
}


# --- payload -> text ---------------------------------------------------------

def build_output(agent: HookAgent, root: Path, payload: dict) -> dict | None:
    """Map one client's hook payload to that client's output, or None.

    Delegates every decision about *what to say* to `claudehook`, so all three
    agents deliver the same freshness, the same warnings, and the same repair
    prompt.
    """
    native = str(payload.get("hook_event_name") or "")
    event = agent.neutral(native)
    if event is None:
        return None

    if event == SESSION_START:
        from . import freshness
        text = claudehook.session_start_text(freshness.evaluate_all(root))
        return agent.envelope(native, text) if text else None

    if event == PRE_TOOL_USE:
        from . import freshness
        rel = claudehook._rel_target(root, payload)
        if rel is None:
            return None
        text = claudehook.pre_tool_use_text(freshness.evaluate_all(root), rel)
        return agent.envelope(native, text) if text else None

    if event == STOP:
        from . import agentcfg, freshness
        # Same two brakes as the Claude path: the client's own "this stop is
        # already the product of a hook" flag, and a per-session note. A Stop
        # hook that speaks unconditionally is a session that never ends.
        if payload.get("stop_hook_active") or payload.get("loop_count"):
            return None
        if not agentcfg.repair_enabled(root):
            return None
        seen = claudehook._seen_path(root, str(
            payload.get("session_id") or payload.get("conversation_id") or ""))
        if claudehook._already_announced(seen, (native, "repair")):
            return None
        text = claudehook.session_end_text(root, freshness.evaluate_all(root))
        return agent.envelope(native, text) if text else None

    return None


def run(agent: HookAgent, root: Path, stdin_text: str) -> str | None:
    """Full hook body. Never raises — the contract every agent shares.

    A hook that raises degrades the session it was meant to inform, so a
    malformed payload, a missing layer, or a bug in here all resolve to
    silence.
    """
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return None
        output = build_output(agent, root, payload)
        return json.dumps(output) if output else None
    except Exception:
        return None


# --- config writing ----------------------------------------------------------

def settings_path(agent: HookAgent, root: Path) -> Path:
    return root / agent.settings


def _load(agent: HookAgent, root: Path) -> dict:
    path = settings_path(agent, root)
    if not path.exists():
        return dict(agent.wrapper)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HookConfigError(
            f"{agent.settings} exists but is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise HookConfigError(f"{agent.settings} exists but is not a JSON object")
    return {**agent.wrapper, **config}


def _ours(command: object) -> bool:
    """Is this hook command Slate's?

    Prefix, not equality: every entry but Claude's carries a `--client` suffix,
    and matching exactly meant a repeated install stacked a second copy instead
    of replacing its own.
    """
    return isinstance(command, str) and command.startswith(HOOK_COMMAND)


def _is_ours(group: dict) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if isinstance(hooks, list):
        return any(isinstance(h, dict) and _ours(h.get("command")) for h in hooks)
    return _ours(group.get("command"))


def _entry(agent: HookAgent, event: str) -> dict:
    """One hook registration in this client's shape."""
    if agent.name == "cursor":
        # Cursor takes a flat list of {command} objects per event.
        return {"command": f"{HOOK_COMMAND} --client cursor"}
    command = HOOK_COMMAND if agent.name == "claude" else f"{HOOK_COMMAND} --client {agent.name}"
    entry: dict = {"hooks": [{"type": "command", "command": command}]}
    if agent.matcher and event == "PreToolUse":
        entry["matcher"] = claudehook.TOOL_MATCHER
    elif agent.matcher:
        entry["matcher"] = ""
    return entry


def install(agent: HookAgent, root: Path) -> Path:
    """Register Slate's hooks for one agent, preserving anyone else's."""
    config = _load(agent, root)
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError(f"{agent.settings} has a non-object hooks key")

    for native in agent.events.values():
        groups = hooks.setdefault(native, [])
        if not isinstance(groups, list):
            raise HookConfigError(
                f"{agent.settings} has a non-array {native} hook list")
        groups[:] = [g for g in groups if not _is_ours(g)]
        groups.append(_entry(agent, native))

    path = settings_path(agent, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def uninstall(agent: HookAgent, root: Path) -> bool:
    config = _load(agent, root)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return False
    removed = False
    for native in list(hooks):
        groups = hooks.get(native)
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not _is_ours(g)]
        if len(kept) != len(groups):
            removed = True
            groups[:] = kept
        if not groups:
            del hooks[native]
    if removed:
        settings_path(agent, root).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return removed


def installed_events(agent: HookAgent, root: Path) -> list[str]:
    try:
        config = _load(agent, root)
    except HookConfigError:
        return []
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [native for native in agent.events.values()
            if isinstance(hooks.get(native), list)
            and any(_is_ours(g) for g in hooks[native])]
