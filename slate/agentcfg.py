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

from .context import SLATE_DIR

READ = "read"
FULL = "full"
MODES = (READ, FULL)

_ACCESS_FILE = f"{SLATE_DIR}/agent-access"


def access_path(root: Path) -> Path:
    return root / _ACCESS_FILE


def get_access(root: Path) -> str:
    """Current access mode; anything missing or unrecognized degrades to read."""
    try:
        mode = access_path(root).read_text().strip().lower()
    except OSError:
        return READ
    return mode if mode in MODES else READ


def set_access(root: Path, mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"access mode must be one of {MODES}, got {mode!r}")
    path = access_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n")


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
            config = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"{rel} exists but is not valid JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise ValueError(f"{rel} exists but is not a JSON object")
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{rel} has a non-object mcpServers key")
    servers["slate"] = dict(SERVER_ENTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    return rel


def enabled_clients(root: Path) -> list[str]:
    """Which known clients already have the slate server registered."""
    found = []
    for client, rel in CLIENTS.items():
        path = root / rel
        if not path.exists():
            continue
        try:
            config = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(config, dict) and "slate" in config.get("mcpServers", {}):
            found.append(client)
    return found
