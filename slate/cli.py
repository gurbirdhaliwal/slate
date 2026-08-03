"""The ``slate`` command-line interface.

Commands (product doc §9):

    slate help      show help for slate or a specific command
    slate ui        interactive dashboard (also: bare `slate` in a terminal)
    slate init      scan the repo and generate the context layer
    slate status    freshness of every context doc (--ci exits 1 on problems)
    slate sync      regenerate auto-blocks, re-anchor freshness to HEAD
                    (--prose adds an LLM-drafted orientation paragraph, opt-in)
    slate mark      attest that a human-owned doc is accurate at HEAD
    slate verify    verification score per doc
    slate read      print the first-read path (what an AI should read, in order)
    slate value     measured savings from slate in this repo (tokens, catches, cost)
    slate diff      what changed vs. what each doc claims; preview of sync
    slate repair    hand-written claims a doc no longer vouches for
    slate watches   show watch globs and propose additions (--apply writes them)
    slate hook      install/uninstall the pre-push freshness gate
    slate merge     install/uninstall the git merge driver for the context layer
    slate mcp       run the MCP server so coding agents can call slate directly
    slate agent     wire slate into agents (enable) + access ceiling (access/status)
    slate fleet     freshness roll-up across multiple repos

Exit codes: 0 ok · 1 freshness problems found (status --ci, fleet --ci) ·
2 usage or environment error (not a git repo, unknown doc, ...).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import (
    __version__,
    agentcfg,
    agenthooks,
    banner,
    claudehook,
    context,
    diffs,
    freshness,
    generator,
    gitutil,
    hooks,
    imports as imports_mod,
    merge as merge_mod,
    repair,
    scanner,
    value,
    verify,
)
from .agentcfg import CLIENTS
from .context import DOC_SPECS, FRESH, NEEDS_VERIFICATION, STALE

STATUS_ICONS = {FRESH: "●", STALE: "○", NEEDS_VERIFICATION: "◐"}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        code = _try_ui(Path(args.repo).resolve())
        if code is not None:
            return code
        print(banner.banner(), end="")
        parser.print_help()
        return 2

    if not getattr(args, "needs_repo", True):
        return args.func(None, args)
    root = _find_root(Path(args.repo).resolve())
    if root is None:
        print("error: not inside a git repository (slate anchors freshness to git)", file=sys.stderr)
        return 2
    return args.func(root, args)


def _try_ui(start: Path) -> int | None:
    """Launch the interactive dashboard for a bare `slate` in a real terminal.

    Returns None when the UI is not applicable (piped output, no TTY, no
    curses, no repo) so the caller falls back to help. A repo without a
    context layer gets the dashboard's welcome screen, which offers init.
    """
    if not (sys.stdout.isatty() and sys.stdin.isatty()):
        return None
    root = _find_root(start)
    if root is None:
        return None
    try:
        from . import ui  # imported lazily: scripted commands never pay for it
    except ImportError:
        return None
    return ui.run(root)


_WORKFLOW_EPILOG = """\
typical workflow:
  slate init                 generate the context layer, then commit it
  ...code changes land...
  slate status               which context docs are now suspect?
  slate diff                 what changed vs. what each doc claims
  slate sync                 regenerate + re-anchor; commit with the code
  slate read                 the ordered first-read path for an AI session

wire into your coding agent:
  slate agent enable claude  register the MCP server (.mcp.json)
  slate agent access full    optional: let the agent maintain the layer

`slate help <command>` shows full options for any command."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slate",
        description="Context control plane for AI-assisted repos.",
        epilog=_WORKFLOW_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"slate {__version__}")
    parser.add_argument("-C", "--repo", default=".", help="repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("help", help="show help for slate or a specific command", description="show help for slate or a specific command")
    p.add_argument("topic", nargs="?", help="command name, e.g. `slate help sync`")
    p.set_defaults(func=cmd_help, needs_repo=False)

    p = sub.add_parser("ui", help="interactive dashboard (also: bare `slate` in a terminal)", description="interactive dashboard: freshness, diffs, sync/mark — built on curses")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("init", help="scan the repo and generate the context layer", description="scan the repo and generate the context layer")
    p.add_argument("--force", action="store_true", help="overwrite existing context docs")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="freshness of every context doc", description="freshness of every context doc")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--ci", action="store_true", help="exit 1 if any doc is not fresh")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("sync", help="regenerate auto-blocks and re-anchor to HEAD", description="regenerate auto-blocks and re-anchor to HEAD")
    p.add_argument("docs", nargs="*", help="doc names (default: all generated docs)")
    p.add_argument(
        "--prose", action="store_true",
        help="add an LLM-drafted orientation paragraph above the scanned facts "
             "(opt-in; needs ANTHROPIC_API_KEY; facts stay deterministic)",
    )
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("mark", help="attest a doc is accurate at HEAD (human-owned docs)", description="attest a doc is accurate at HEAD (human-owned docs)")
    p.add_argument("docs", nargs="+", help="doc names, e.g. read-next decisions")
    p.add_argument("--allow-claim-loss", action="store_true",
                   help="attest even though claims present at the last anchor "
                        "are gone (they are named first; use when the prose is "
                        "genuinely obsolete)")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("verify", help="verification score (0.00-1.00) per doc", description="verification score (0.00-1.00) per doc")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("read", help="print the first-read path for an AI session", description="print the first-read path for an AI session")
    p.add_argument("--paths", action="store_true", help="print file paths only")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser(
        "value",
        help="measured savings from slate in this repo (tokens, catches, cost)",
        description="cumulative value ledger: context served vs. measured re-exploration, "
                    "stale docs caught before use, and what deterministic syncs replaced. "
                    "Measured events only; cost estimates are labeled with their assumptions.",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_value)

    p = sub.add_parser("diff", help="what changed vs. what each doc claims (+ sync preview)", description="what changed vs. what each doc claims (+ sync preview)")
    p.add_argument("docs", nargs="*", help="doc names (default: every doc that isn't fresh)")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser(
        "repair",
        help="hand-written claims a doc no longer vouches for",
        description="the suspect hand-written claims, strongest evidence first, each "
                    "with the refs that put it at risk and the commits behind them. "
                    "Lists only — generated facts are omitted because `slate sync` "
                    "already rewrites them deterministically.",
    )
    p.add_argument("docs", nargs="*", help="doc names (default: all)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_repair)

    p = sub.add_parser("watches", help="show watch globs and propose additions", description="show watch globs and propose additions")
    p.add_argument("docs", nargs="*", help="doc names (default: all)")
    p.add_argument("--apply", action="store_true", help="write proposed watches into the docs")
    p.set_defaults(func=cmd_watches)

    p = sub.add_parser("hook", help="manage the pre-push freshness gate", description="manage the pre-push freshness gate")
    p.add_argument("action", choices=["install", "uninstall"])
    p.add_argument("--force", action="store_true", help="overwrite a non-slate pre-push hook")
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser(
        "merge",
        help="manage the git merge driver for the context layer",
        description="git merge driver: 3-way-merges hand-written text across branches "
                    "and lets `slate sync` regenerate the facts, so concurrent PRs stop "
                    "conflicting in the context layer (and stop losing each other's notes)",
    )
    merge_sub = p.add_subparsers(dest="merge_command", required=True)
    q = merge_sub.add_parser("install", help="register the driver (git config) + .gitattributes", description="register the driver in this clone and add the .gitattributes lines (commit them to share)")
    q.set_defaults(func=cmd_merge_install)
    q = merge_sub.add_parser("uninstall", help="remove the driver and the .gitattributes lines", description="remove the driver and the .gitattributes lines")
    q.set_defaults(func=cmd_merge_uninstall)
    q = merge_sub.add_parser("status", help="show which half of the wiring is present", description="show which half of the wiring is present (.gitattributes is committed; the driver is per-clone)")
    q.add_argument("--json", action="store_true", help="machine-readable output")
    q.set_defaults(func=cmd_merge_status)
    q = merge_sub.add_parser("run", help="the driver itself (git invokes this; not for humans)", description=f"the merge driver git invokes: {merge_mod.DRIVER_COMMAND}")
    q.add_argument("base")
    q.add_argument("ours")
    q.add_argument("theirs")
    q.add_argument("path")
    q.set_defaults(func=cmd_merge_run, needs_repo=False)

    p = sub.add_parser("mcp", help="run the MCP server (stdio) so coding agents can call slate", description="run the MCP server (stdio) so coding agents can call slate")
    p.add_argument(
        "--access", choices=["read", "full"], default=None,
        help="override the repo's agent access mode for this session",
    )
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("agent", help="wire slate into coding agents (MCP) and manage access", description="wire slate into coding agents (MCP) and manage access")
    agent_sub = p.add_subparsers(dest="agent_command", required=True)
    q = agent_sub.add_parser("enable", help="register the slate MCP server with a client", description="register the slate MCP server with a client")
    q.add_argument("client", choices=[*sorted(CLIENTS), "all"], help="which editor/agent to wire up")
    q.add_argument("--full", action="store_true", help="also grant full (write) access")
    q.add_argument("--no-hooks", action="store_true",
                   help="skip the Claude Code freshness hooks (MCP + instruction bridge only)")
    q.set_defaults(func=cmd_agent_enable)
    q = agent_sub.add_parser("access", help="get or set the agent access ceiling", description="get or set the agent access ceiling")
    q.add_argument("mode", nargs="?", choices=["read", "full"], help="omit to show current mode")
    q.set_defaults(func=cmd_agent_access)
    q = agent_sub.add_parser(
        "repair",
        help="get or set whether the agent may rewrite suspect claims",
        description="doc repair is a second switch on top of full access, because "
                    "it edits prose a human wrote in response to a job the human "
                    "never gave. Both must be on before anything is written.",
    )
    q.add_argument("state", nargs="?", choices=["on", "off"], help="omit to show current state")
    q.set_defaults(func=cmd_agent_repair)
    q = agent_sub.add_parser("status", help="show wiring + access mode", description="show wiring + access mode")
    q.add_argument("--json", action="store_true", help="machine-readable output")
    q.set_defaults(func=cmd_agent_status)
    q = agent_sub.add_parser(
        "hook",
        help="the Claude Code hook handler (Claude Code invokes this; not for humans)",
        description="reads a hook payload on stdin and emits freshness as injected "
                    "context: the whole layer's trust state at SessionStart, and a "
                    "warning at PreToolUse when the file being touched is covered by "
                    "a doc that is not fresh. Always exits 0 — a hook must never be "
                    "the reason a session breaks.",
    )
    q.add_argument("--client", choices=sorted(agenthooks.AGENTS),
                   default="claude",
                   help="which agent's payload shape to speak (default claude)")
    q.set_defaults(func=cmd_agent_hook)
    q = agent_sub.add_parser(
        "hooks",
        help="install/uninstall the freshness hooks for a coding agent",
        description="manage slate's hook entries in the agent's own config "
                    "(committed and shared with the team). Claude Code, Codex "
                    "and Cursor deliver the same freshness; only the envelope "
                    "differs. Delivery is canary-verified for Claude Code only.",
    )
    q.add_argument("action", choices=["install", "uninstall", "status"])
    q.add_argument("--client", choices=[*sorted(agenthooks.AGENTS), "all"],
                   default="claude")
    q.set_defaults(func=cmd_agent_hooks)

    p = sub.add_parser("fleet", help="freshness roll-up across multiple repos", description="freshness roll-up across multiple repos")
    p.add_argument(
        "paths", nargs="*",
        help="repo paths, or parent dirs to scan one level deep (default: cwd's children)",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--ci", action="store_true", help="exit 1 if any repo has problems")
    p.set_defaults(func=cmd_fleet, needs_repo=False)

    parser.slate_subcommands = sub.choices  # used by cmd_help
    return parser


def _find_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate if gitutil.is_git_repo(candidate) else None
    return None


# --- commands ---------------------------------------------------------------

def cmd_init(root: Path, args: argparse.Namespace) -> int:
    existing = [s.rel_path for s in DOC_SPECS if s.path(root).exists()]
    if existing and not args.force:
        print("context layer already exists; `slate sync` to refresh or --force to regenerate:")
        for path in existing:
            print(f"  {path}")
        return 2
    # Written before the scan so the scan counts it: a file that appears after
    # the facts are generated leaves the doc describing a tree that no longer
    # exists, and the very next sync would rewrite it.
    bridge = agentcfg.bridge_claude(root)
    scan = scanner.scan(root)
    written = generator.generate_all(scan, force=args.force)
    print(f"initialized context layer at {gitutil.head_commit(root) or '(no commits yet)'}:")
    for path in written:
        print(f"  wrote {path}")
    _print_claude_bridge(bridge)
    print("\nnext: fill in the (human) sections, then commit the context layer.")
    return 0


def _print_claude_bridge(result: str) -> None:
    """Say which happened.

    Staying quiet here would reproduce the exact failure the bridge exists to
    fix: a layer that looks installed and is never read.
    """
    if result == agentcfg.WROTE:
        print(f"  wrote {agentcfg.CLAUDE_BRIDGE} (imports AGENTS.md — Claude "
              f"Code does not read AGENTS.md itself)")
    elif result == agentcfg.MANUAL:
        print(f"\n! {agentcfg.CLAUDE_BRIDGE} exists but does not import the layer.")
        print(f"  Claude Code reads {agentcfg.CLAUDE_BRIDGE}, not AGENTS.md, so it "
              f"will not see this context layer.")
        print(f"  Add this line to {agentcfg.CLAUDE_BRIDGE}: {agentcfg.BRIDGE_IMPORT}")


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    reports = freshness.evaluate_all(root)
    if not reports:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([
            {
                "doc": r.doc.spec.name,
                "path": r.rel_path,
                "status": r.status,
                "reason": r.reason,
                "changed_watched": r.changed_watched,
                "content_verified": r.content_verified,
                "claims": [_claim_json(c) for c in r.claims],
            }
            for r in reports
        ], indent=2))
    else:
        width = max(len(r.rel_path) for r in reports) + 2
        for r in reports:
            icon = STATUS_ICONS[r.status]
            print(f"{icon} {r.rel_path:<{width}} {r.status:<20} {r.reason}")
            for path in r.changed_watched[:5]:
                print(f"    ↳ {path}")
            if len(r.changed_watched) > 5:
                print(f"    ↳ … and {len(r.changed_watched) - 5} more")
            # The novel Part B signal: which hand-written claim is now suspect.
            human_suspect = [c for c in r.suspect_claims if c.kind == "human"]
            for c in human_suspect[:3]:
                marker = "?" if c.status == freshness.CLAIM_UNKNOWABLE else "✗"
                print(f"    {marker} {_claim_line(c)}")
            if len(human_suspect) > 3:
                print(f"    … and {len(human_suspect) - 3} more suspect claim(s)")
    caught = value.record_catches(root, reports)
    if not args.json and (footer := value.catches_footer(caught)):
        print(f"\n{footer}")
    problems = [r for r in reports if r.status != FRESH]
    if args.ci and problems:
        print(f"\n{len(problems)} doc(s) not fresh", file=sys.stderr)
        return 1
    return 0


def cmd_sync(root: Path, args: argparse.Namespace) -> int:
    docs = context.load_all(root)
    if not docs:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    selected = _select(docs, args.docs)
    if selected is None:
        return 2
    if not args.docs:
        selected = [d for d in selected if d.spec.generated]

    prose = None
    if args.prose:
        from . import llm  # imported only on the opt-in path
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("error: --prose needs ANTHROPIC_API_KEY in the environment", file=sys.stderr)
            return 2
        prose = llm.prose_writer(api_key)

    # Backfill for repos initialised before the bridge existed — they have run
    # `init` already and would otherwise keep shipping Claude Code nothing.
    # Before the scan, so the regenerated facts count it (see cmd_init).
    bridge = agentcfg.bridge_claude(root)

    # Measured before the sync: what the manual AI-rewrite workflow would have
    # had to read/write for the docs that are actually stale right now.
    reports = {r.doc.spec.name: r for r in freshness.evaluate_all(root)}
    baseline = value.sync_baseline(root, reports, [d.spec.name for d in selected])

    scan = scanner.scan(root)
    with value.timer() as t:
        for doc in selected:
            try:
                generator.sync_doc(doc, scan, prose=prose)
            except Exception as exc:
                from .llm import ProseError
                if not isinstance(exc, ProseError):
                    raise
                # Prose is additive — never let it block the deterministic sync.
                print(f"warning: prose skipped for {doc.spec.rel_path}: {exc}", file=sys.stderr)
                generator.sync_doc(doc, scan)
            print(f"synced {doc.spec.rel_path}")
    _print_claude_bridge(bridge)
    skipped = [d.spec.name for d in docs if d not in selected and not d.spec.generated]
    if not args.docs and skipped:
        print(f"human-owned docs untouched ({', '.join(skipped)}) — review and `slate mark` them")
    if footer := value.sync_footer(value.record_sync(root, baseline, t.ms)):
        print(footer)
    return 0


def cmd_mark(root: Path, args: argparse.Namespace) -> int:
    docs = context.load_all(root)
    selected = _select(docs, args.docs)
    if selected is None:
        return 2

    # Attesting is the one moment a doc's trust is renewed by assertion rather
    # than by evidence, so it is the one moment a silently deleted claim would
    # never be noticed again. Refuse and name them; a human who meant it says
    # so with --allow-claim-loss.
    if not getattr(args, "allow_claim_loss", False):
        blocked = False
        for doc in selected:
            loss = repair.claim_loss(root, doc)
            if not loss.dropped:
                continue
            blocked = True
            print(
                f"error: {doc.spec.rel_path} has {loss.dropped} fewer claim(s) "
                f"than at {doc.synced_commit} ({loss.before} → {loss.after}), "
                f"so marking it verified would retire them with nothing having "
                f"checked. No longer present:", file=sys.stderr)
            for text in loss.vanished[:5]:
                trimmed = text if len(text) <= 100 else text[:99] + "…"
                print(f"  - {trimmed}", file=sys.stderr)
            if len(loss.vanished) > 5:
                print(f"  … and {len(loss.vanished) - 5} more", file=sys.stderr)
        if blocked:
            print("\nRestore them, or re-run with --allow-claim-loss if the "
                  "prose is genuinely obsolete.", file=sys.stderr)
            return 2

    commit = gitutil.head_commit(root)
    for doc in selected:
        context.stamp(root, doc, commit)
        context.save(root, doc)
        print(f"marked {doc.spec.rel_path} verified at {commit or '(no commits yet)'}")
    return 0


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    results = verify.verify_all(root)
    if not results:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([
            {
                "doc": v.report.doc.spec.name,
                "path": v.rel_path,
                "status": v.report.status,
                "score": v.score,
                "referenced_paths": v.referenced,
                "missing_paths": v.missing,
                "total_claims": v.total_claims,
                "suspect_claims": v.suspect_claims,
            }
            for v in results
        ], indent=2))
        return 0
    width = max(len(v.rel_path) for v in results) + 2
    for v in results:
        icon = STATUS_ICONS[v.report.status]
        bar = _bar(v.score)
        tail = ""
        if v.suspect_claims:
            tail = f"  {v.total_claims - v.suspect_claims}/{v.total_claims} claims check out"
        print(f"{icon} {v.rel_path:<{width}} {v.score:.2f} {bar}{tail}")
        for path in v.missing[:5]:
            print(f"    ✗ references missing path: {path}")
    return 0


def cmd_read(root: Path, args: argparse.Namespace) -> int:
    reports = {r.doc.spec.name: r for r in freshness.evaluate_all(root)}
    if not reports:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    ordered = sorted(
        (s for s in DOC_SPECS if s.read_order and s.name in reports),
        key=lambda s: s.read_order,
    )
    measured = value.record_session(root)
    value.record_catches(root, reports.values())
    if args.paths:
        for spec in ordered:
            print(spec.rel_path)
        return 0
    print("first-read path (read in order; trust per status):\n")
    for i, spec in enumerate(ordered, 1):
        r = reports[spec.name]
        icon = STATUS_ICONS[r.status]
        print(f"{i}. {icon} {spec.rel_path} [{r.status}] — {spec.title}")
    if footer := value.session_footer(measured):
        print(f"\n{footer}")
    return 0


def cmd_value(root: Path, args: argparse.Namespace) -> int:
    t = value.totals(root)
    if args.json:
        print(json.dumps(t, indent=2))
        return 0
    m = t["measured"]
    if not (m["sessions_served"] or m["syncs_run"] or m["stale_docs_caught"]):
        print(
            "no value recorded in this clone yet — slate keeps a measured receipt\n"
            "of every `read`, `status`, and `sync` as you work; check back after a\n"
            "few sessions (ledger: " + t["assumptions"]["ledger"] + ")"
        )
        return 0
    print(value.render_report(t))
    return 0


def cmd_diff(root: Path, args: argparse.Namespace) -> int:
    docs = context.load_all(root)
    if not docs:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    selected = _select(docs, args.docs)
    if selected is None:
        return 2
    scan = scanner.scan(root)
    results = [diffs.doc_diff(root, doc, scan) for doc in selected]
    if not args.docs:
        results = [d for d in results if d.report.status != FRESH]
    if not results:
        print("everything fresh — nothing to diff")
        return 0
    for d in results:
        icon = STATUS_ICONS[d.report.status]
        print(f"\n{icon} {d.rel_path} [{d.report.status}] — {d.report.reason}")
        if d.changes:
            kinds = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed"}
            print("  watched changes:")
            for path, kind in d.changes.items():
                print(f"    {kind}  {path}  ({kinds.get(kind, kind)})")
        if d.suspect_claims:
            print("  claims put at risk (the specific sentence + what threatens it):")
            for c in d.suspect_claims:
                marker = "?" if c.status == freshness.CLAIM_UNKNOWABLE else "✗"
                print(f"    {marker} {_claim_line(c)}")
                if c.risk:
                    print(f"        risk: {', '.join(c.risk)}")
        if d.missing_refs:
            print("  broken claims (doc references paths that no longer exist):")
            for ref in d.missing_refs:
                print(f"    ✗ {ref}")
        if d.sync_preview:
            print("  what `slate sync` would change:")
            for line in d.sync_preview:
                print(f"    {line}")
        elif d.report.doc.spec.generated and d.report.status != FRESH:
            print("  auto-block already matches a fresh scan — `slate sync` would just re-anchor")
    caught = value.record_catches(root, [d.report for d in results])
    if footer := value.catches_footer(caught):
        print(f"\n{footer}")
    return 0


def cmd_repair(root: Path, args: argparse.Namespace) -> int:
    reports = freshness.evaluate_all(root)
    if not reports:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    if args.docs:
        wanted = set(args.docs)
        reports = [r for r in reports if r.doc.spec.name in wanted or r.rel_path in wanted]
        if not reports:
            print(f"no such doc: {', '.join(sorted(wanted))}", file=sys.stderr)
            return 2
    tasks = repair.repair_tasks(root, reports)

    if args.json:
        print(json.dumps([t.as_dict() for t in tasks], indent=2))
        return 0
    if not tasks:
        print("no hand-written claim is suspect — nothing to repair")
        return 0

    for task in tasks:
        strength = "symbol moved" if task.evidence_is_strong else "file changed"
        print(f"{task.doc_path}:{task.line}  [{task.status} · {strength}]  {task.section}")
        text = task.text if len(task.text) <= 88 else task.text[:87] + "…"
        print(f"  {text}")
        for ref in task.risk:
            sha = task.commits.get(ref)
            where = f"  ({sha[:7]})" if sha else (
                "  (working tree)" if ref in task.uncommitted else "")
            print(f"  ↳ {ref}{where}")
        if task.anchor:
            print(f"  since {task.anchor}")
        print()
    weak = sum(1 for t in tasks if not t.evidence_is_strong)
    print(f"{len(tasks)} claim(s) to check, {weak} on file-level evidence only "
          "— those may already be correct.")
    return 0


def cmd_watches(root: Path, args: argparse.Namespace) -> int:
    docs = context.load_all(root)
    if not docs:
        print("no context layer found — run `slate init`", file=sys.stderr)
        return 2
    selected = _select(docs, args.docs)
    if selected is None:
        return 2
    scan = scanner.scan(root)
    edges = imports_mod.import_edges(scan)
    proposed_any = False
    for doc in selected:
        suggestions = imports_mod.suggest(root, doc, scan, edges)
        current = ", ".join(doc.watches) or "(none — attestation-based)"
        print(f"{doc.spec.rel_path}")
        print(f"  watches: {current}")
        for s in suggestions:
            proposed_any = True
            print(f"  + {s.pattern}  — {s.reason}")
        if suggestions and args.apply:
            doc.meta["slate_watches"] = doc.watches + [s.pattern for s in suggestions]
            context.save(root, doc)
            print(f"  applied {len(suggestions)} watch(es)")
    if proposed_any and not args.apply:
        print("\nrun `slate watches --apply` to add the proposed watches")
    return 0


def cmd_hook(root: Path, args: argparse.Namespace) -> int:
    try:
        if args.action == "install":
            path = hooks.install(root, force=args.force)
            print(f"installed pre-push freshness gate at {path}")
        else:
            if hooks.uninstall(root):
                print("pre-push hook removed")
            else:
                print("no slate pre-push hook installed")
    except hooks.HookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_merge_install(root: Path, args: argparse.Namespace) -> int:
    try:
        merge_mod.install(root)
    except (merge_mod.MergeError, gitutil.GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"registered the slate merge driver in this clone ({merge_mod.DRIVER_CONFIG})")
    print(f"wrote {merge_mod.ATTRIBUTES_FILE} — commit it so the whole team gets it")
    print(
        "\nEach teammate also runs `slate merge install` once: .gitattributes is\n"
        "committed, but the driver command is git config and stays per-clone.\n"
        "Without it git falls back to its built-in merge — no worse than before."
    )
    return 0


def cmd_merge_uninstall(root: Path, args: argparse.Namespace) -> int:
    try:
        removed = merge_mod.uninstall(root)
    except (merge_mod.MergeError, gitutil.GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("merge driver removed" if removed else "no slate merge driver installed")
    return 0


def cmd_merge_status(root: Path, args: argparse.Namespace) -> int:
    info = {
        "driver": merge_mod.driver_registered(root),
        "attributes": merge_mod.attributes_registered(root),
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    driver = "registered" if info["driver"] else "not registered (this clone)"
    attrs = "present" if info["attributes"] else "absent"
    print(f"driver ({merge_mod.DRIVER_CONFIG}): {driver}")
    print(f"{merge_mod.ATTRIBUTES_FILE}: {attrs}")
    if not (info["driver"] and info["attributes"]):
        print("\nrun `slate merge install` to complete the wiring")
    return 0


def cmd_merge_run(_root: Path | None, args: argparse.Namespace) -> int:
    """The driver git calls per conflicted file. Never raises at git."""
    try:
        code, message = merge_mod.run(
            Path(args.base), Path(args.ours), Path(args.theirs), args.path
        )
    except (merge_mod.MergeError, gitutil.GitError, OSError) as exc:
        # Failing here would abort the merge; leave the file conflicted with
        # ours' content and let the human resolve it by hand.
        print(f"slate: {args.path}: merge driver failed ({exc})", file=sys.stderr)
        return 1
    if message:
        print(message, file=sys.stderr)
    return code


def cmd_help(_root: Path | None, args: argparse.Namespace) -> int:
    parser = _build_parser()
    if not args.topic:
        print(banner.banner(), end="")
        parser.print_help()
        return 0
    subcommand = parser.slate_subcommands.get(args.topic)
    if subcommand is None:
        known = ", ".join(sorted(parser.slate_subcommands))
        print(f"error: unknown command '{args.topic}' (known: {known})", file=sys.stderr)
        return 2
    subcommand.print_help()
    return 0


def cmd_ui(root: Path, args: argparse.Namespace) -> int:
    try:
        from . import ui  # imported lazily: scripted commands never pay for it
    except ImportError:
        print("error: the interactive UI needs the curses module (not available on this platform)", file=sys.stderr)
        return 2
    return ui.run(root)


def cmd_mcp(root: Path, args: argparse.Namespace) -> int:
    from . import mcp  # imported here so plain CLI use never pays for it
    return mcp.serve(root, access=args.access)


def cmd_agent_enable(root: Path, args: argparse.Namespace) -> int:
    clients = sorted(CLIENTS) if args.client == "all" else [args.client]
    for client in clients:
        try:
            rel = agentcfg.enable_client(root, client)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"registered slate MCP server for {client}: wrote {rel}")
        if client == "claude" and (root / "AGENTS.md").exists():
            # The MCP tools are opt-in — the agent has to choose to call them.
            # The instruction file is what it reads unprompted, so wiring the
            # server without the bridge leaves the layer invisible by default.
            _print_claude_bridge(agentcfg.bridge_claude(root))
            # The bridge only gets the prose into the window. It does nothing
            # about the agent declining to call slate_status — measured at 0
            # calls in 320 (benchmarks/agentbench/RESULTS.md). The hooks are
            # what make the freshness signal non-optional.
            if not args.no_hooks:
                try:
                    path = claudehook.install(root)
                    print(f"  wrote {path.relative_to(root)} (SessionStart + "
                          f"PreToolUse freshness hooks — the agent no longer has "
                          f"to ask for freshness)")
                except claudehook.HookConfigError as exc:
                    print(f"\n! could not install the freshness hooks: {exc}")
                    print("  Fix that file (or pass --no-hooks) and re-run.")
    if args.full:
        agentcfg.set_access(root, agentcfg.FULL)
    mode = agentcfg.get_access(root)
    print(f"\nagent access: {mode}")
    if mode == agentcfg.READ:
        print("  read-only — the agent can read context and freshness, not change it.")
        print("  Grant write access (sync/mark/focus/decisions): slate agent access full")
    else:
        print("  full — the agent may sync, mark, and update read-next/decisions.")
    print(
        "\nYour editor still asks permission per tool call (Claude Code-style)\n"
        "unless you always-allow a tool there. Slate's access mode is the hard\n"
        "ceiling underneath; commit .slate/agent-access to make it team policy.\n"
        "Restart the editor session so it picks up the new MCP server."
    )
    return 0


def cmd_agent_access(root: Path, args: argparse.Namespace) -> int:
    if args.mode:
        agentcfg.set_access(root, args.mode)
        print(f"agent access set to {args.mode} ({agentcfg.access_path(root).relative_to(root)})")
        return 0
    print(agentcfg.get_access(root))
    return 0


def cmd_agent_repair(root: Path, args: argparse.Namespace) -> int:
    if args.state:
        agentcfg.set_repair(root, args.state)
        print(f"agent repair set to {args.state} "
              f"({agentcfg.repair_path(root).relative_to(root)})")
        if args.state == agentcfg.REPAIR_ON and agentcfg.get_access(root) != agentcfg.FULL:
            # Deliberately not an error: the user asked for one of the two
            # switches and got it. Saying nothing would leave them believing
            # repair is live when it is not.
            print("  note: agent access is still read-only, so nothing can be "
                  "written yet — `slate agent access full` throws the other switch.")
        return 0
    print(agentcfg.get_repair(root))
    return 0


def cmd_agent_status(root: Path, args: argparse.Namespace) -> int:
    info = {
        "access": agentcfg.get_access(root),
        "repair": agentcfg.get_repair(root),
        "repair_effective": agentcfg.repair_enabled(root),
        "clients": agentcfg.enabled_clients(root),
        "hooks": claudehook.installed_events(root),
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"access: {info['access']}")
    print(f"repair: {info['repair']}"
          + ("" if info["repair_effective"] else " (not in effect — needs full access)"))
    if info["clients"]:
        print(f"wired clients: {', '.join(info['clients'])}")
    else:
        print("wired clients: none — run `slate agent enable claude` (or cursor/all)")
    if info["hooks"]:
        print(f"claude hooks: {', '.join(info['hooks'])}")
    else:
        print("claude hooks: none — freshness only reaches the agent if it "
              "chooses to ask (`slate agent hooks install`)")
    return 0


def cmd_agent_hook(root: Path, args: argparse.Namespace) -> int:
    """The hook body an agent invokes. Always exits 0, and never raises.

    `root` is the repo containing the cwd; the clients also pass `cwd` in the
    payload, but trusting our own resolution keeps the hook working when the
    agent has cd'd into a subdirectory.

    The try/except is not belt-and-braces. `claudehook.run` and
    `agenthooks.run` each swallow their own failures, but *this* function sits
    above them and a bug here reaches the client as a crashing hook — which is
    exactly what happened: a typo'd variable name raised a NameError before
    either handler was reached, and the unit tests missed it because they call
    the handlers directly. Silence costs a signal; a traceback costs the
    session.
    """
    try:
        # Claude Code keeps its own entry point: that path is canary-verified
        # and pinned by 47 tests, and routing it through the generic adapter
        # would trade measured behaviour for tidiness.
        client = getattr(args, "client", "claude")
        if client == "claude":
            output = claudehook.run(root, sys.stdin.read())
        else:
            output = agenthooks.run(agenthooks.AGENTS[client], root,
                                    sys.stdin.read())
        if output:
            print(output)
    except Exception:
        pass
    return 0


def _claude_hooks(root: Path, action: str) -> None:
    if action == "install":
        path = claudehook.install(root)
        print(f"claude: installed freshness hooks in {path.relative_to(root)}")
        print(f"  {claudehook.SESSION_START}: layer freshness at session start "
              f"(and after compaction)")
        print(f"  {claudehook.PRE_TOOL_USE}: warns on {claudehook.TOOL_MATCHER} "
              f"when the target file is covered by a non-fresh doc")
        print(f"  {claudehook.STOP}: names the claims this session left suspect "
              f"(inert until `slate agent repair on`)")
    elif action == "uninstall":
        print("claude: " + ("removed slate's hook entries"
                            if claudehook.uninstall(root)
                            else "no slate hooks installed"))
    else:
        events = claudehook.installed_events(root)
        print("claude: " + (", ".join(events) if events
                            else "no slate hooks installed"))


def cmd_agent_hooks(root: Path, args: argparse.Namespace) -> int:
    clients = sorted(agenthooks.AGENTS) if args.client == "all" else [args.client]
    try:
        for client in clients:
            if client == "claude":
                _claude_hooks(root, args.action)
                continue
            agent = agenthooks.AGENTS[client]
            if args.action == "install":
                path = agenthooks.install(agent, root)
                native = ", ".join(agent.events.values())
                print(f"installed freshness hooks in {path.relative_to(root)} "
                      f"({native})")
                if agent.beta:
                    print(f"  note: {client} hooks are beta, and Slate's "
                          f"delivery there is built from the published contract "
                          f"rather than observed end to end")
                if client == "cursor":
                    print("  note: cursor's beforeReadFile cannot inject "
                          "context, so the file warning rides preToolUse; "
                          "slate never sends a permission decision")
            elif args.action == "uninstall":
                print(f"{client}: "
                      + ("removed slate's hook entries"
                         if agenthooks.uninstall(agent, root)
                         else "no slate hooks installed"))
            else:
                events = agenthooks.installed_events(agent, root)
                print(f"{client}: " + (", ".join(events) if events
                                       else "no slate hooks installed"))
        if args.action == "install":
            print("\nCommit these files to share the hooks with the team.")
            print("Restart the agent session to pick them up.")
    except (claudehook.HookConfigError, agenthooks.HookConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_fleet(_root: Path | None, args: argparse.Namespace) -> int:
    roots = gitutil.fleet_roots([Path(p) for p in args.paths] or [Path.cwd()])
    if not roots:
        print("no git repositories found", file=sys.stderr)
        return 2
    rows = []
    for repo in roots:
        reports = freshness.evaluate_all(repo)
        if not reports:
            rows.append({"repo": str(repo), "layer": False,
                         "fresh": 0, "stale": 0, "needs_verification": 0})
            continue
        counts = {FRESH: 0, STALE: 0, NEEDS_VERIFICATION: 0}
        for r in reports:
            counts[r.status] += 1
        rows.append({
            "repo": str(repo), "layer": True, "fresh": counts[FRESH],
            "stale": counts[STALE], "needs_verification": counts[NEEDS_VERIFICATION],
        })
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        width = max(len(r["repo"]) for r in rows) + 2
        for r in rows:
            if not r["layer"]:
                print(f"· {r['repo']:<{width}} no context layer (run `slate init`)")
                continue
            icon = "●" if r["stale"] + r["needs_verification"] == 0 else "○"
            print(
                f"{icon} {r['repo']:<{width}} "
                f"fresh {r['fresh']} · stale {r['stale']} · needs-verification {r['needs_verification']}"
            )
    problems = [r for r in rows if r["layer"] and (r["stale"] or r["needs_verification"])]
    if args.ci and problems:
        print(f"\n{len(problems)} repo(s) with freshness problems", file=sys.stderr)
        return 1
    return 0


def _select(docs: list[context.ContextDoc], names: list[str]) -> list[context.ContextDoc] | None:
    if not names:
        return docs
    by_name = {d.spec.name: d for d in docs} | {d.spec.rel_path: d for d in docs}
    selected = []
    for name in names:
        doc = by_name.get(name)
        if doc is None:
            known = ", ".join(sorted({d.spec.name for d in docs}))
            print(f"error: unknown doc '{name}' (known: {known})", file=sys.stderr)
            return None
        selected.append(doc)
    return selected


def _bar(score: float, width: int = 20) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _claim_line(c: "freshness.ClaimVerdict", limit: int = 72) -> str:
    text = c.text if len(c.text) <= limit else c.text[: limit - 1] + "…"
    where = f" [{c.section}]" if c.section and c.section != "(generated facts)" else ""
    return f"{text}{where}"


def _claim_json(c: "freshness.ClaimVerdict") -> dict:
    return c.as_dict()


if __name__ == "__main__":
    sys.exit(main())
