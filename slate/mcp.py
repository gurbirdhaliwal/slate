"""MCP server — wires Slate directly into coding agents.

Speaks the Model Context Protocol over stdio (newline-delimited JSON-RPC
2.0), which is what Claude Code, Cursor, and VS Code agent mode consume.
Once registered (``slate agent enable``), the agent calls tools like
``slate_read`` itself — no more copy-pasting CLI output into the chat.

Consent model (see agentcfg.py): the *client* prompts the user per tool
call (or the user always-allows, Claude Code-style); Slate's access mode
is the hard ceiling underneath. In ``read`` mode the mutating tools are
not exposed at all.

The server is a thin adapter: every tool delegates to the same library
code the CLI uses, and returns the same JSON shapes as the ``--json``
flags. No trust math lives here.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import IO

from . import (
    __version__,
    agentcfg,
    context,
    diffs,
    freshness,
    generator,
    gitutil,
    imports as imports_mod,
    repair,
    scanner,
    value,
    verify,
)
from .context import DOC_SPECS, FRESH

PROTOCOL_VERSION = "2025-06-18"

_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INVALID_PARAMS = -32602
_JSONRPC_PARSE_ERROR = -32700

_NO_LAYER = (
    "No context layer found in this repo. Initializing one is the user's "
    "decision — suggest they run `slate init`, don't do it for them."
)

_WRITE_DENIED = (
    "Slate agent access is read-only in this repo, so this tool is disabled. "
    "The user can grant write access with `slate agent access full` (or the "
    "'Slate: Agent Access' toggle in VS Code); `.slate/agent-access` is the "
    "committed policy file."
)

_REPAIR_DENIED = (
    "Slate doc repair is off in this repo, so this tool is disabled. It is a "
    "second switch on top of full access, because repair edits prose a human "
    "wrote. The user can turn it on with `slate agent repair on`; "
    "`.slate/agent-repair` is the committed policy file. Report the suspect "
    "claims instead and let them decide."
)


class SlateMCPServer:
    """One instance per stdio session. ``handle`` is pure enough to test."""

    def __init__(self, root: Path, access: str | None = None) -> None:
        self.root = root
        self._access_override = access

    @property
    def access(self) -> str:
        # Re-read per call so a toggle takes effect without restarting the
        # server (clients keep stdio servers alive for a whole session).
        return self._access_override or agentcfg.get_access(self.root)

    # --- JSON-RPC plumbing ---------------------------------------------

    def handle(self, msg: dict) -> dict | None:
        """Handle one JSON-RPC message; None for notifications."""
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            return _result(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "slate", "version": __version__},
                "instructions": (
                    "Slate maintains this repo's context layer. Call slate_read "
                    "at the start of a session for the trusted first-read path; "
                    "call slate_status before relying on a context doc mid-task."
                ),
            })
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": self._tool_specs()})
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            try:
                text, is_error = self._call(name, args)
            except Exception as exc:  # a tool bug must not kill the session
                text, is_error = f"slate internal error in {name}: {exc}", True
            content = {"content": [{"type": "text", "text": text}], "isError": is_error}
            return _result(msg_id, content)
        if method.startswith("notifications/"):
            return None
        if msg_id is None:
            return None  # unknown notification — ignore per spec
        return _error(msg_id, _JSONRPC_METHOD_NOT_FOUND, f"method not found: {method}")

    # --- tool registry ---------------------------------------------------

    def _tool_specs(self) -> list[dict]:
        tools = [
            _tool(
                "slate_read",
                "Read the repo's context layer in its intended order, with a trust "
                "label per doc (fresh / stale / needs-verification) and verification "
                "scores. Call this FIRST in a session instead of rediscovering the "
                "repo. Treat stale docs as claims to verify, not facts.",
                {"include_contents": {
                    "type": "boolean",
                    "description": "Include each doc's Markdown body (default true).",
                }},
            ),
            _tool(
                "slate_status",
                "Freshness of every context doc right now (includes uncommitted "
                "changes). Use before trusting a doc mid-task, or after making "
                "code changes to see which docs you invalidated.",
                {},
            ),
            _tool(
                "slate_verify",
                "Verification score (0.00-1.00) per context doc, with any broken "
                "path references. Higher = safer to trust.",
                {},
            ),
            _tool(
                "slate_diff",
                "For each non-fresh doc: which watched paths changed (added/"
                "modified/deleted/renamed), which of the doc's claims broke, and "
                "a preview of what slate_sync would rewrite.",
                {},
            ),
            _tool(
                "slate_repair_tasks",
                "The hand-written claims the code no longer vouches for: the "
                "sentence, where it lives, the refs that put it at risk and the "
                "commits behind them. Strongest evidence first. A task is NOT "
                "proof the prose is wrong — 'this claim is still correct' is a "
                "valid answer and usually the right one for path-scoped evidence.",
                {},
            ),
            _tool(
                "slate_watches",
                "Watch globs per context doc (the paths whose changes make the "
                "doc suspect) plus proposed additions derived from the repo's "
                "import graph. Pass apply=true (needs full access) to write the "
                "proposals into the docs.",
                {"apply": {
                    "type": "boolean",
                    "description": "Apply the proposed watches (default false; requires full access).",
                }},
            ),
        ]
        if self.access == agentcfg.FULL:
            tools += [
                _tool(
                    "slate_sync",
                    "Regenerate the auto-generated blocks of the context docs from "
                    "a fresh repo scan and re-anchor their freshness to HEAD. Run "
                    "after completing a task that changed watched code. Human-"
                    "written sections are never touched.",
                    {"docs": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Doc names to sync (default: all generated docs).",
                    }},
                ),
                _tool(
                    "slate_mark",
                    "Attest that human-owned docs (read-next, decisions) are "
                    "accurate at the current commit. Only call after actually "
                    "reviewing or updating them.",
                    {"docs": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Doc names, e.g. [\"read-next\"].",
                    }},
                    required=["docs"],
                ),
                _tool(
                    "slate_update_focus",
                    "Rewrite the 'Current focus' (and optionally 'Landmines') "
                    "section of .slate/read-next.md and mark it verified. Call at "
                    "the END of a session so the next session starts from reality.",
                    {
                        "current_focus": {
                            "type": "string",
                            "description": "What is in flight now / what comes next. Concise Markdown.",
                        },
                        "landmines": {
                            "type": "string",
                            "description": "Gotchas and rejected approaches worth warning about.",
                        },
                    },
                    required=["current_focus"],
                ),
                _tool(
                    "slate_append_decision",
                    "Append an entry to .slate/decisions.md (append-only log) and "
                    "mark it verified. Use when a real decision was made that a "
                    "future session would otherwise re-litigate.",
                    {
                        "decision": {"type": "string"},
                        "rationale": {"type": "string"},
                        "trade_off": {"type": "string"},
                        "revisit_trigger": {"type": "string"},
                    },
                    required=["decision", "rationale"],
                ),
            ]
            if agentcfg.repair_enabled(self.root):
                tools.append(_tool(
                    "slate_repair_apply",
                    "Replace one suspect claim with a rewrite, after Slate "
                    "verifies the edit. The rewrite MUST still name code in "
                    "backticks — a sentence with no refs stops being a checkable "
                    "claim at all, and that edit is refused. Only the target "
                    "claim may change. Leaving an accurate claim alone is a "
                    "correct outcome; do not call this to make a flag go away.",
                    {
                        "doc": {
                            "type": "string",
                            "description": "Doc name, e.g. \"read-next\".",
                        },
                        "target": {
                            "type": "string",
                            "description": "The claim text exactly as slate_repair_tasks reported it.",
                        },
                        "replacement": {
                            "type": "string",
                            "description": "The rewritten claim. Must name code in backticks.",
                        },
                    },
                    required=["doc", "target", "replacement"],
                ))
        return tools

    _WRITE_TOOLS = {"slate_sync", "slate_mark", "slate_update_focus",
                    "slate_append_decision", "slate_repair_apply"}

    def _call(self, name: str, args: dict) -> tuple[str, bool]:
        if name in self._WRITE_TOOLS and self.access != agentcfg.FULL:
            return _WRITE_DENIED, True
        if name == "slate_watches" and args.get("apply") and self.access != agentcfg.FULL:
            return _WRITE_DENIED, True
        # Full access is not enough on its own. It was granted for sync/mark/
        # focus — none of which touch prose the user wrote in response to a job
        # the user never gave.
        if name == "slate_repair_apply" and not agentcfg.repair_enabled(self.root):
            return _REPAIR_DENIED, True
        handlers = {
            "slate_read": self._t_read,
            "slate_status": self._t_status,
            "slate_verify": self._t_verify,
            "slate_diff": self._t_diff,
            "slate_repair_tasks": self._t_repair_tasks,
            "slate_repair_apply": self._t_repair_apply,
            "slate_watches": self._t_watches,
            "slate_sync": self._t_sync,
            "slate_mark": self._t_mark,
            "slate_update_focus": self._t_update_focus,
            "slate_append_decision": self._t_append_decision,
        }
        handler = handlers.get(name)
        if handler is None:
            return f"unknown tool: {name}", True
        return handler(args)

    # --- read tools -------------------------------------------------------

    def _t_read(self, args: dict) -> tuple[str, bool]:
        reports = {r.doc.spec.name: r for r in freshness.evaluate_all(self.root)}
        if not reports:
            return _NO_LAYER, True
        scores = {v.report.doc.spec.name: v.score for v in verify.verify_all(self.root)}
        include = args.get("include_contents", True)
        ordered = sorted(
            (s for s in DOC_SPECS if s.read_order and s.name in reports),
            key=lambda s: s.read_order,
        )
        docs = []
        for spec in ordered:
            r = reports[spec.name]
            entry = {
                "doc": spec.name,
                "path": spec.rel_path,
                "title": spec.title,
                "status": r.status,
                "score": scores.get(spec.name),
                "reason": r.reason,
            }
            if include:
                loaded = context.load(self.root, spec)
                entry["contents"] = loaded.body if loaded else None
            docs.append(entry)
        payload = {
            "read_in_order": docs,
            "trust_protocol": (
                "fresh: safe to rely on. stale: watched code changed since the doc "
                "was synced — verify against the code before acting. "
                "needs-verification: freshness anchor lost and content unverifiable "
                "— treat as a rumor."
            ),
        }
        measured = value.record_session(self.root)
        value.record_catches(self.root, reports.values())
        if measured:  # additive field: what this read saved vs. re-exploring (measured sizes)
            payload["value"] = {
                "context_tokens": measured["context_tokens"],
                "exploration_baseline_tokens": measured["baseline_tokens"],
                "note": "measured file sizes; " + value.BASELINE_NOTE,
            }
        return json.dumps(payload, indent=2), False

    def _t_status(self, _args: dict) -> tuple[str, bool]:
        reports = freshness.evaluate_all(self.root)
        if not reports:
            return _NO_LAYER, True
        value.record_catches(self.root, reports)
        return json.dumps([
            {
                "doc": r.doc.spec.name,
                "path": r.rel_path,
                "status": r.status,
                "reason": r.reason,
                "changed_watched": r.changed_watched,
                "content_verified": r.content_verified,
                "claims": [c.as_dict() for c in r.claims],
            }
            for r in reports
        ], indent=2), False

    def _t_verify(self, _args: dict) -> tuple[str, bool]:
        results = verify.verify_all(self.root)
        if not results:
            return _NO_LAYER, True
        return json.dumps([
            {
                "doc": v.report.doc.spec.name,
                "path": v.rel_path,
                "status": v.report.status,
                "score": v.score,
                "missing_paths": v.missing,
                "total_claims": v.total_claims,
                "suspect_claims": v.suspect_claims,
            }
            for v in results
        ], indent=2), False

    def _t_diff(self, _args: dict) -> tuple[str, bool]:
        docs = context.load_all(self.root)
        if not docs:
            return _NO_LAYER, True
        scan = scanner.scan(self.root)
        results = [diffs.doc_diff(self.root, doc, scan) for doc in docs]
        suspect = [d for d in results if d.report.status != FRESH]
        value.record_catches(self.root, [d.report for d in results])
        if not suspect:
            return json.dumps({"message": "everything fresh — nothing to diff"}), False
        return json.dumps([
            {
                "doc": d.report.doc.spec.name,
                "path": d.rel_path,
                "status": d.report.status,
                "watched_changes": d.changes,
                "broken_claims": d.missing_refs,
                "suspect_claims": [c.as_dict() for c in d.suspect_claims],
                "sync_preview": d.sync_preview,
            }
            for d in suspect
        ], indent=2), False

    def _t_watches(self, args: dict) -> tuple[str, bool]:
        docs = context.load_all(self.root)
        if not docs:
            return _NO_LAYER, True
        scan = scanner.scan(self.root)
        edges = imports_mod.import_edges(scan)
        apply = bool(args.get("apply"))
        out = []
        for doc in docs:
            suggestions = imports_mod.suggest(self.root, doc, scan, edges)
            entry = {
                "doc": doc.spec.name,
                "path": doc.spec.rel_path,
                "watches": doc.watches,
                "proposed": [
                    {"pattern": s.pattern, "reason": s.reason} for s in suggestions
                ],
            }
            if apply and suggestions:
                doc.meta["slate_watches"] = doc.watches + [s.pattern for s in suggestions]
                context.save(self.root, doc)
                entry["applied"] = len(suggestions)
            out.append(entry)
        return json.dumps(out, indent=2), False

    # --- write tools (access: full) ----------------------------------------

    def _t_sync(self, args: dict) -> tuple[str, bool]:
        docs = context.load_all(self.root)
        if not docs:
            return _NO_LAYER, True
        names = args.get("docs") or []
        if names:
            by_name = {d.spec.name: d for d in docs}
            missing = [n for n in names if n not in by_name]
            if missing:
                return f"unknown docs: {', '.join(missing)}", True
            selected = [by_name[n] for n in names]
        else:
            selected = [d for d in docs if d.spec.generated]
        reports = {r.doc.spec.name: r for r in freshness.evaluate_all(self.root)}
        baseline = value.sync_baseline(self.root, reports, [d.spec.name for d in selected])
        scan = scanner.scan(self.root)
        with value.timer() as t:
            for doc in selected:
                generator.sync_doc(doc, scan)
        synced = [d.spec.rel_path for d in selected]
        payload = {
            "synced": synced,
            "anchored_at": gitutil.head_commit(self.root),
            "note": "Doc changes are unstaged — commit them with the code change.",
        }
        event = value.record_sync(self.root, baseline, t.ms)
        if event and event["healed"]:  # additive field: measured receipt for this sync
            payload["value"] = {
                "healed_stale_docs": event["healed"],
                "elapsed_ms": event["elapsed_ms"],
                "tokens_spent": 0,
                "manual_rewrite_tokens_measured": {
                    "input": event["manual_input_tokens"],
                    "output": event["manual_output_tokens"],
                },
            }
        return json.dumps(payload, indent=2), False

    def _t_repair_tasks(self, args: dict) -> tuple[str, bool]:
        reports = freshness.evaluate_all(self.root)
        if not reports:
            return _NO_LAYER, True
        tasks = repair.repair_tasks(self.root, reports)
        return json.dumps({
            "tasks": [t.as_dict() for t in tasks],
            "note": (
                "A task means the code a claim names changed, not that the claim "
                "is false. `symbol` scope is strong evidence; `path` scope often "
                "is not. Deciding a claim is still correct is a valid outcome."
            ),
        }, indent=2), False

    def _t_repair_apply(self, args: dict) -> tuple[str, bool]:
        """Verify a rewrite, then write it — or refuse and say why.

        The engine decides, never the caller. `verify_repair` is the same gate
        `slate repair` would apply by hand, and the doc is only touched after it
        returns something other than `rejected`.

        The doc is *not* re-anchored here. A repair is newer prose by
        definition, so `freshness` would clear it on authorship alone whatever
        it says — re-stamping would be Slate vouching for text it never checked.
        Whoever reviews the diff runs `slate mark`.
        """
        name = (args.get("doc") or "").strip()
        target = (args.get("target") or "").strip()
        replacement = (args.get("replacement") or "").strip()
        if not name or not target or not replacement:
            return "doc, target and replacement are required", True
        try:
            spec = context.spec_by_name(name)
        except (KeyError, ValueError):
            return f"unknown doc: {name}", True
        doc = context.load(self.root, spec)
        if doc is None:
            return _NO_LAYER, True

        before = doc.body
        after = repair.replace_claim(before, target, replacement)
        verdict = repair.verify_repair(before, after, target)
        payload = verdict.as_dict()
        payload["doc"] = spec.rel_path
        if not verdict.ok:
            payload["note"] = (
                "Nothing was written. Fix the rewrite or leave the claim alone — "
                "an accurate claim is allowed to stay as it is."
            )
            return json.dumps(payload, indent=2), True

        if verdict.outcome == repair.REPAIRED:
            doc.body = after
            context.save(self.root, doc)
        payload["note"] = (
            "Doc change is unstaged and the doc was NOT re-anchored — freshness "
            "cannot score a repair (it is newer prose by definition). Review the "
            "diff, then `slate mark` if it is right."
        )
        return json.dumps(payload, indent=2), False

    def _t_mark(self, args: dict) -> tuple[str, bool]:
        names = args.get("docs") or []
        if not names:
            return "docs is required", True
        docs = context.load_all(self.root)
        by_name = {d.spec.name: d for d in docs}
        missing = [n for n in names if n not in by_name]
        if missing:
            return f"unknown docs: {', '.join(missing)}", True
        commit = gitutil.head_commit(self.root)
        for name in names:
            doc = by_name[name]
            context.stamp(self.root, doc, commit)
            context.save(self.root, doc)
        return json.dumps({"marked": names, "verified_at": commit}, indent=2), False

    def _t_update_focus(self, args: dict) -> tuple[str, bool]:
        focus = (args.get("current_focus") or "").strip()
        if not focus:
            return "current_focus is required", True
        spec = context.spec_by_name("read-next")
        doc = context.load(self.root, spec)
        if doc is None:
            return _NO_LAYER, True
        doc.body = replace_section(doc.body, "## Current focus", focus)
        landmines = (args.get("landmines") or "").strip()
        if landmines:
            doc.body = replace_section(doc.body, "## Landmines", landmines)
        commit = gitutil.head_commit(self.root)
        context.stamp(self.root, doc, commit)
        context.save(self.root, doc)
        return json.dumps({
            "updated": spec.rel_path,
            "verified_at": commit,
            "sections": ["Current focus"] + (["Landmines"] if landmines else []),
        }, indent=2), False

    def _t_append_decision(self, args: dict) -> tuple[str, bool]:
        decision = (args.get("decision") or "").strip()
        rationale = (args.get("rationale") or "").strip()
        if not decision or not rationale:
            return "decision and rationale are required", True
        spec = context.spec_by_name("decisions")
        doc = context.load(self.root, spec)
        if doc is None:
            return _NO_LAYER, True
        lines = [f"Date: {date.today().isoformat()}", f"Decision: {decision}", f"Rationale: {rationale}"]
        if args.get("trade_off"):
            lines.append(f"Trade-off: {str(args['trade_off']).strip()}")
        if args.get("revisit_trigger"):
            lines.append(f"Revisit trigger: {str(args['revisit_trigger']).strip()}")
        entry = "\n```\n" + "\n".join(lines) + "\n```\n"
        doc.body = doc.body.rstrip("\n") + "\n" + entry
        commit = gitutil.head_commit(self.root)
        context.stamp(self.root, doc, commit)
        context.save(self.root, doc)
        return json.dumps({"appended_to": spec.rel_path, "verified_at": commit}, indent=2), False


def replace_section(body: str, heading: str, new_text: str) -> str:
    """Replace the content under ``heading`` up to the next ## heading.

    If the heading is missing (a human restructured the doc), the section is
    appended at the end rather than guessing — never destroy what's there.
    """
    lines = body.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return body.rstrip("\n") + f"\n\n{heading}\n\n{new_text.strip()}\n"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    replaced = lines[: start + 1] + ["", new_text.strip(), ""] + lines[end:]
    text = "\n".join(replaced)
    return text if text.endswith("\n") else text + "\n"


# --- stdio loop --------------------------------------------------------------

def serve(root: Path, access: str | None = None,
          stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> int:
    """Run the newline-delimited JSON-RPC loop until stdin closes."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    server = SlateMCPServer(root, access)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _write(stdout, _error(None, _JSONRPC_PARSE_ERROR, "parse error"))
            continue
        response = server.handle(msg)
        if response is not None:
            _write(stdout, response)
    return 0


def _write(stdout: IO[str], response: dict) -> None:
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
