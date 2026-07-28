"""`slate agent hook` — freshness delivered as context, not as an offer.

Slate's MCP server exposes `slate_status`, and `AGENTS.md` instructs the
agent to call it first. Measured against 25 real headless sessions
(`benchmarks/agentbench/RESULTS.md`), the agent made **0 calls to any
`slate_*` tool across 320 tool calls** — while the server reported
`connected` and every tool was exposed. The freshness engine, which is the
entire product thesis, went unexercised by every session that had it
available.

That is not a bug in the agent. A signal delivered as an *optional tool
call* is a signal that competes with grep, and grep wins: it is cheaper and
it always returns something. The fix is to stop asking. Claude Code hooks
run as ordinary subprocesses at fixed lifecycle points, and their stdout is
injected into the model's context whether or not the model wanted it.

Two events, doing two different jobs:

- **SessionStart** — states the freshness of the whole layer once, up
  front, so "which of these docs can I trust" is answered before the agent
  forms a plan. Fires with an empty matcher, which also covers `compact`:
  compaction is exactly when a summarized layer loses its freshness
  qualifiers and the docs start reading as unconditionally true.
- **PreToolUse** — fires on `Read`/`Edit`/`Write`/`NotebookEdit` and speaks
  only when the file being touched is *covered by the watches of a doc that
  is not fresh*. Just-in-time, scoped to the file at hand, and silent
  otherwise; a warning that fires on every tool call is a banner, and
  banners are skimmed.

**This module computes no trust math.** It calls `freshness.evaluate_all`
and renders the result, exactly as `cli` and `mcp` do. The rule that the
MCP server must never fork the trust path (`tests/test_mcp.py`) applies
here for the same reason: a second implementation of "is this doc fresh"
is a second thing that can disagree with the first, and the disagreement
would surface as a confident sentence in the model's context.

**Failure is silence, never a false `fresh`.** Every entry point is wrapped:
on any exception, a missing layer, or a path outside the repo, the hook
emits nothing and exits 0. Silence costs the agent the signal for one tool
call; the alternatives are worse in both directions — a crash would make
Slate the reason a session broke, and a cheerful default would vouch for
content this module never checked. Nothing here ever prints "fresh" for a
doc it failed to evaluate. `tests/test_claude_hook.py` pins this.

Cost: a PreToolUse evaluation is ~380ms on this repo, of which ~57ms is
interpreter start — it is real work (a repo scan plus a git diff), not
startup overhead. It is deliberately uncached. A cache in the warning path
is a mechanism for suppressing a warning that should have fired, which is
the one failure mode §10 forbids, and 380ms sits inside the noise of a
tool-call round trip. Revisit only with a measurement that says it hurts.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import context, freshness, globs
from .context import CONTEXT_DOC_PATHS, FRESH, NEEDS_VERIFICATION, STALE

SESSION_START = "SessionStart"
PRE_TOOL_USE = "PreToolUse"

# Tools whose target file is worth checking against watch coverage. Read is
# included on purpose: the damage a stale doc does is done at the moment the
# agent believes it, which is usually a read, not a write.
WATCHED_TOOLS = ("Read", "Edit", "Write", "NotebookEdit")
TOOL_MATCHER = "|".join(WATCHED_TOOLS)

# Co-change is announced on *edits* only. Reading a file asks "what is here";
# changing it is the moment "what else moves with this" becomes actionable,
# and it is the moment the benchmark showed agents getting wrong — every
# revision-3 trial edited `app.py` and none opened `sessions.py`.
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")

HOOK_COMMAND = "slate agent hook"

# Keep injected text bounded. This lands in every session (SessionStart) or
# potentially every file touch (PreToolUse); an unbounded render would make
# Slate the thing eating the context window it claims to economize.
_MAX_DOCS_LISTED = 8
_MAX_CLAIMS = 2
_MAX_PATHS = 3


# --- rendering --------------------------------------------------------------

def _describe(report: freshness.DocReport) -> str:
    """One line for a non-fresh doc, naming why it is suspect."""
    line = f"  {report.rel_path} — {report.status}: {report.reason}"
    changed = report.changed_watched[:_MAX_PATHS]
    if changed:
        more = len(report.changed_watched) - len(changed)
        tail = f" (+{more} more)" if more > 0 else ""
        line += f"\n      changed: {', '.join(changed)}{tail}"
    return line


def session_start_text(reports: list[freshness.DocReport]) -> str | None:
    """The whole layer's trust state, stated once at session start.

    Returns None when there is no layer to describe. The all-fresh case is
    *not* silent: "these docs were verified against this commit" is the
    positive half of the signal, and an agent that only ever hears from
    Slate when something is wrong learns to treat the docs as unqualified
    the rest of the time.
    """
    if not reports:
        return None

    problems = [r for r in reports if r.status != FRESH]
    lines = ["Slate context layer — freshness checked at session start:"]

    if not problems:
        names = ", ".join(r.rel_path for r in reports[:_MAX_DOCS_LISTED])
        lines.append(
            f"  All {len(reports)} context docs are fresh — their claims were "
            f"verified against the current commit."
        )
        lines.append(f"  Docs: {names}")
        lines.append(
            "  You can rely on them as written. Read them before exploring; "
            "they are cheaper and more current than re-deriving the same facts."
        )
        return "\n".join(lines)

    fresh_docs = [r for r in reports if r.status == FRESH]
    lines.append(
        f"  {len(problems)} of {len(reports)} docs are NOT fresh. "
        "Do not trust the docs below without checking the code first:"
    )
    lines.extend(_describe(r) for r in problems[:_MAX_DOCS_LISTED])
    if len(problems) > _MAX_DOCS_LISTED:
        lines.append(f"  … and {len(problems) - _MAX_DOCS_LISTED} more non-fresh doc(s)")

    if fresh_docs:
        lines.append(
            f"  Fresh (safe to rely on): "
            f"{', '.join(r.rel_path for r in fresh_docs[:_MAX_DOCS_LISTED])}"
        )
    lines.append(
        "  `slate diff` shows what changed; `slate sync` re-anchors the "
        "generated facts."
    )
    return "\n".join(lines)


def _covering(
    reports: list[freshness.DocReport], rel_path: str
) -> list[freshness.DocReport]:
    """Non-fresh docs whose watches cover this path.

    Human-owned docs carry no watches (`context.default_watches` returns []
    for them) and `globs.any_match([], path)` is False, so they can never
    match here — correct, since their freshness is attestation-based and
    says nothing about any particular file.
    """
    return [
        r
        for r in reports
        if r.status != FRESH and r.doc.watches and globs.any_match(r.doc.watches, rel_path)
    ]


def pre_tool_use_text(
    reports: list[freshness.DocReport], rel_path: str
) -> str | None:
    """Warn only when this specific file is covered by a suspect doc."""
    if rel_path in CONTEXT_DOC_PATHS:
        return None  # editing the layer itself; the agent is healing it
    covering = _covering(reports, rel_path)
    if not covering:
        return None

    lines = [
        f"Slate: {rel_path} is covered by {len(covering)} context doc(s) that "
        f"are not fresh."
    ]
    for report in covering[:_MAX_DOCS_LISTED]:
        lines.append(f"  {report.rel_path} — {report.status}: {report.reason}")
        suspect = [c for c in report.suspect_claims if c.kind == "human"]
        for claim in suspect[:_MAX_CLAIMS]:
            text = claim.text.strip().replace("\n", " ")
            if len(text) > 160:
                text = text[:157] + "…"
            lines.append(f"      suspect claim: {text}")
    lines.append(
        "  Statements in those docs about this file may describe code that has "
        "since changed. Verify against the source before relying on them."
    )
    return "\n".join(lines)


# --- co-change: the same fact, delivered at the moment it applies -----------
# Measured: rendering this into `architecture.md` does nothing. In the
# revision-3 sweep the layer named `src/flask/app.py` <-> `src/flask/
# sessions.py` — the exact coupling every trial missed — and every trial
# still missed it, whether or not it opened the doc. A fact filed in a
# document the agent may read is a fact the agent may not read. The same
# sentence, injected at the instant the agent edits `app.py`, is not
# something it can skip.
#
# Announced once per pair per session. A warning that repeats on every edit
# to the same file is a banner, and banners are the failure mode this exists
# to escape — so the fired pairs are recorded per session in the clone-local
# state dir, best-effort, and a bookkeeping failure costs a duplicate warning
# rather than the hook.

_MAX_PARTNERS = 3


def _seen_path(root: Path, session_id: str) -> Path | None:
    from . import gitutil

    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
    if not safe:
        return None
    try:
        return gitutil.state_dir(root) / "cochange-seen" / f"{safe}.json"
    except Exception:
        return None


def _already_announced(path: Path | None, pair: tuple[str, str]) -> bool:
    """Has this pair been announced in this session? Records it if not."""
    if path is None:
        return False
    key = "|".join(pair)
    try:
        seen = set(json.loads(path.read_text())) if path.exists() else set()
    except (OSError, json.JSONDecodeError, TypeError):
        seen = set()
    if key in seen:
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(seen | {key})))
    except OSError:
        pass  # a lost note costs a repeat warning, never the hook
    return False


def cochange_text(root: Path, rel_path: str, session_id: str) -> str | None:
    """Warn that history couples this file to others, once per pair."""
    from . import cochange, gitutil

    if not cochange.enabled():
        return None
    partners = cochange.partners(root, gitutil.list_files(root), rel_path,
                                 limit=_MAX_PARTNERS)
    if not partners:
        return None

    seen = _seen_path(root, session_id)
    fresh = [
        (other, n) for other, n in partners
        if not _already_announced(seen, tuple(sorted((rel_path, other))))
    ]
    if not fresh:
        return None

    lines = [
        f"Slate: {rel_path} has historically changed together with "
        f"{'this file' if len(fresh) == 1 else 'these files'}:"
    ]
    lines += [f"  {other} — same commit {n}x" for other, n in fresh]
    lines.append(
        "  That is history, not a rule: it is often the difference between a "
        "change that works and one that is complete. Check whether your edit "
        "needs a counterpart there before moving on."
    )
    return "\n".join(lines)


# --- payload handling -------------------------------------------------------

def _rel_target(root: Path, payload: dict) -> str | None:
    """Repo-relative POSIX path of the file a tool call targets, if any."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        target = Path(raw)
        if not target.is_absolute():
            target = root / target
        return target.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None  # outside the repo, or unresolvable — not ours to speak about


def _output(event: str, text: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": text,
        }
    }


def build_output(root: Path, payload: dict) -> dict | None:
    """Map a hook payload to hook output, or None to stay silent.

    Pure apart from reading the repo, so tests drive it directly rather than
    through a subprocess.
    """
    event = payload.get("hook_event_name")
    if event not in (SESSION_START, PRE_TOOL_USE):
        return None

    if event == PRE_TOOL_USE:
        # Cheap rejections before the ~380ms evaluation: most tool calls are
        # neither file-targeting nor inside the repo.
        if payload.get("tool_name") not in WATCHED_TOOLS:
            return None
        rel_path = _rel_target(root, payload)
        if rel_path is None:
            return None

        parts = []
        stale = pre_tool_use_text(freshness.evaluate_all(root), rel_path)
        if stale:
            parts.append(stale)
        # Only on edits, and only outside the layer itself. Ordered after the
        # staleness warning: "this doc may be lying to you" outranks "you may
        # not be finished".
        if payload.get("tool_name") in EDIT_TOOLS and rel_path not in CONTEXT_DOC_PATHS:
            coupled = cochange_text(root, rel_path,
                                    str(payload.get("session_id", "")))
            if coupled:
                parts.append(coupled)
        return _output(PRE_TOOL_USE, "\n\n".join(parts)) if parts else None

    text = session_start_text(freshness.evaluate_all(root))
    return _output(SESSION_START, text) if text else None


def run(root: Path, stdin_text: str) -> str | None:
    """Full hook body: parse, evaluate, render. Never raises.

    A hook that raises is a hook that degrades the session it was meant to
    inform, so every failure — malformed payload, no context layer, a bug in
    this module — resolves to silence.
    """
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return None
        output = build_output(root, payload)
        return json.dumps(output) if output else None
    except Exception:
        return None


# --- settings.json wiring ---------------------------------------------------
# {"hooks": {<Event>: [{"matcher": str, "hooks": [{"type","command"}]}]}}
# Project-scoped hooks live in .claude/settings.json, which is committed and
# shared. That is why the command is the bare `slate agent hook` rather than an
# absolute interpreter path: an absolute path would be correct on the machine
# that ran install and wrong for every teammate who checks the file out. Same
# trade-off, and the same PATH assumption, as the MCP server entry.

SETTINGS_FILE = ".claude/settings.json"

_ENTRIES = {
    SESSION_START: "",           # every source, including `compact`
    PRE_TOOL_USE: TOOL_MATCHER,
}


class HookConfigError(RuntimeError):
    pass


def settings_path(root: Path) -> Path:
    return root / SETTINGS_FILE


def _load_settings(root: Path) -> dict:
    path = settings_path(root)
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HookConfigError(f"{SETTINGS_FILE} exists but is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise HookConfigError(f"{SETTINGS_FILE} exists but is not a JSON object")
    return config


def _is_ours(group: dict) -> bool:
    """Does this hook group invoke slate? Identified by command, so a repeated
    install replaces its own entry instead of stacking duplicates."""
    if not isinstance(group, dict):
        return False
    return any(
        isinstance(h, dict) and h.get("command") == HOOK_COMMAND
        for h in group.get("hooks", [])
        if isinstance(group.get("hooks"), list)
    )


def install(root: Path) -> Path:
    """Register both hooks, merging into any existing settings.

    Only slate's own entries are touched; other tools' hooks on the same
    events are preserved.
    """
    config = _load_settings(root)
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError(f"{SETTINGS_FILE} has a non-object hooks key")

    for event, matcher in _ENTRIES.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise HookConfigError(f"{SETTINGS_FILE} has a non-array {event} hook list")
        groups[:] = [g for g in groups if not _is_ours(g)]
        groups.append({
            "matcher": matcher,
            "hooks": [{"type": "command", "command": HOOK_COMMAND}],
        })

    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def uninstall(root: Path) -> bool:
    """Remove slate's hook entries. False if none were present."""
    config = _load_settings(root)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return False

    removed = False
    for event in list(hooks):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not _is_ours(g)]
        if len(kept) != len(groups):
            removed = True
            groups[:] = kept
        if not groups:
            del hooks[event]
    if not hooks:
        config.pop("hooks", None)

    if removed:
        settings_path(root).write_text(json.dumps(config, indent=2) + "\n")
    return removed


def installed_events(root: Path) -> list[str]:
    """Which slate hook events are wired up in this repo."""
    try:
        config = _load_settings(root)
    except HookConfigError:
        return []
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [
        event
        for event in _ENTRIES
        if isinstance(hooks.get(event), list)
        and any(_is_ours(g) for g in hooks[event])
    ]
