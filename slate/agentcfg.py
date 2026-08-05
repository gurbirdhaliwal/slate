"""Agent access control — the hard ceiling on what a coding agent may do.

Two layers of consent govern agent access to Slate (product doc §9):

1. **The client's permission prompts** (Claude Code, Cursor, ...) — the UX
   layer. The editor asks the user before each tool call unless the user
   has always-allowed it. Slate does not reimplement this.
2. **Slate's access mode** — the capability ceiling this module owns.
   In ``read`` mode (the default) the MCP server does not even expose the
   mutating tools, so no client bug or over-eager always-allow can change
   the context layer. ``full`` unlocks sync/mark/focus/decision tools.

The mode lives in ``.slate/agent-access`` as a single word so it is
diff-reviewable and can be a deliberate, committed team policy.
"""

from __future__ import annotations

import json
from pathlib import Path

from .context import CLAUDE_BRIDGE, SLATE_DIR

READ = "read"
FULL = "full"
MODES = (READ, FULL)

_ACCESS_FILE = f"{SLATE_DIR}/agent-access"


def access_path(root: Path) -> Path:
    return root / _ACCESS_FILE


def get_access(root: Path) -> str:
    """Current access mode; anything missing or unrecognized degrades to read."""
    try:
        mode = access_path(root).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return READ
    return mode if mode in MODES else READ


def set_access(root: Path, mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"access mode must be one of {MODES}, got {mode!r}")
    path = access_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n", encoding="utf-8")


# --- repair (Phase 3) -------------------------------------------------------
# A third switch, deliberately separate from the access mode. `full` already
# lets an agent sync, mark, and rewrite read-next — all of which a user asked
# for by granting it. Repair is different in kind: it edits prose the user
# wrote, in response to a job the user never gave. An agent silently editing
# tracked files is how a tool gets uninstalled once, so this starts off and
# both switches must be thrown before anything writes.

REPAIR_ON = "on"
REPAIR_OFF = "off"
REPAIR_STATES = (REPAIR_ON, REPAIR_OFF)

_REPAIR_FILE = f"{SLATE_DIR}/agent-repair"


def repair_path(root: Path) -> Path:
    return root / _REPAIR_FILE


def get_repair(root: Path) -> str:
    """The repair switch on its own; anything missing or unrecognized is off."""
    try:
        state = repair_path(root).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return REPAIR_OFF
    return state if state in REPAIR_STATES else REPAIR_OFF


def set_repair(root: Path, state: str) -> None:
    if state not in REPAIR_STATES:
        raise ValueError(f"repair must be one of {REPAIR_STATES}, got {state!r}")
    path = repair_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state + "\n", encoding="utf-8")


def repair_enabled(root: Path) -> bool:
    """Both switches, and the conjunction is the point.

    Turning repair on while access is read must grant nothing — otherwise the
    repair file becomes a way around the access ceiling, which is the one thing
    that ceiling exists to be.
    """
    return get_repair(root) == REPAIR_ON and get_access(root) == FULL


# --- client registration ----------------------------------------------------
# Each entry: (config file rel path, top-level key). Both Claude Code and
# Cursor use the same {"mcpServers": {name: {command, args}}} shape.

CLIENTS: dict[str, str] = {
    "claude": ".mcp.json",         # Claude Code project-scoped MCP config
    "cursor": ".cursor/mcp.json",  # Cursor project MCP config
}

SERVER_ENTRY = {"command": "slate", "args": ["mcp"]}


def enable_client(root: Path, client: str) -> str:
    """Register the slate MCP server in a client's project config.

    Merges into an existing config rather than replacing it; only the
    ``slate`` server entry is ever written. Returns the rel path written.
    """
    rel = CLIENTS[client]
    path = root / rel
    config: dict = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{rel} exists but is not valid JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise ValueError(f"{rel} exists but is not a JSON object")
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{rel} has a non-object mcpServers key")
    servers["slate"] = dict(SERVER_ENTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return rel


# --- Claude Code instruction bridge -----------------------------------------
# Claude Code loads CLAUDE.md, never AGENTS.md — it treats AGENTS.md as another
# tool's format and only reads it when importing from Codex. A repo whose whole
# context layer hangs off AGENTS.md therefore ships Claude Code nothing at all,
# silently: the MCP tools still connect, the docs still sit in the tree, and
# none of it reaches the model. The documented remedy is a CLAUDE.md that
# `@`-imports the layer, which is what this writes.
# See https://code.claude.com/docs/en/memory ("AGENTS.md").

BRIDGE_IMPORT = "@AGENTS.md"

# Block-level HTML comments are stripped before CLAUDE.md is injected, so the
# explanation costs the reader nothing and the import is the only content.
_BRIDGE_BODY = f"""\
<!--
  Written by Slate. Claude Code reads CLAUDE.md, not AGENTS.md, so this file
  imports the context layer. Commit it alongside AGENTS.md. Add any
  Claude-specific instructions below the import.
  https://code.claude.com/docs/en/memory
-->
{BRIDGE_IMPORT}
"""

WROTE = "wrote"
ALREADY = "already"
MANUAL = "manual"


def _imports_layer(text: str) -> bool:
    """Does this CLAUDE.md already pull in AGENTS.md?

    Deliberately literal: an import inside a code fence does not count for
    Claude Code either, and anything cleverer would risk reporting a bridge
    that is not actually live.
    """
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if not fenced and stripped.startswith(BRIDGE_IMPORT):
            return True
    return False


def bridge_claude(root: Path) -> str:
    """Ensure Claude Code can see the layer. Never clobbers a user's file.

    Returns ``WROTE`` (created the bridge), ``ALREADY`` (it was there), or
    ``MANUAL`` — a CLAUDE.md exists that does not import the layer, so the
    caller must tell the human rather than overwrite their instructions.
    """
    path = root / CLAUDE_BRIDGE
    if not path.exists():
        path.write_text(_BRIDGE_BODY, encoding="utf-8")
        return WROTE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return MANUAL
    return ALREADY if _imports_layer(text) else MANUAL


def enabled_clients(root: Path) -> list[str]:
    """Which known clients already have the slate server registered."""
    found = []
    for client, rel in CLIENTS.items():
        path = root / rel
        if not path.exists():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(config, dict) and "slate" in config.get("mcpServers", {}):
            found.append(client)
    return found
