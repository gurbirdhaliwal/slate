"""The ``slate`` command-line interface.

Commands (product doc §9):

    slate init      scan the repo and generate the context layer
    slate status    freshness of every context doc (--ci exits 1 on problems)
    slate sync      regenerate auto-blocks, re-anchor freshness to HEAD
                    (--prose adds an LLM-drafted orientation paragraph, opt-in)
    slate mark      attest that a human-owned doc is accurate at HEAD
    slate verify    verification score per doc
    slate read      print the first-read path (what an AI should read, in order)
    slate diff      what changed vs. what each doc claims; preview of sync
    slate watches   show watch globs and propose additions (--apply writes them)
    slate hook      install/uninstall the pre-push freshness gate
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
    context,
    diffs,
    freshness,
    generator,
    gitutil,
    hooks,
    imports as imports_mod,
    scanner,
    verify,
)
from .context import DOC_SPECS, FRESH, NEEDS_VERIFICATION, STALE

STATUS_ICONS = {FRESH: "●", STALE: "○", NEEDS_VERIFICATION: "◐"}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    if not getattr(args, "needs_repo", True):
        return args.func(None, args)
    root = _find_root(Path(args.repo).resolve())
    if root is None:
        print("error: not inside a git repository (slate anchors freshness to git)", file=sys.stderr)
        return 2
    return args.func(root, args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slate",
        description="Context control plane for AI-assisted repos.",
    )
    parser.add_argument("--version", action="version", version=f"slate {__version__}")
    parser.add_argument("-C", "--repo", default=".", help="repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="scan the repo and generate the context layer")
    p.add_argument("--force", action="store_true", help="overwrite existing context docs")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="freshness of every context doc")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--ci", action="store_true", help="exit 1 if any doc is not fresh")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("sync", help="regenerate auto-blocks and re-anchor to HEAD")
    p.add_argument("docs", nargs="*", help="doc names (default: all generated docs)")
    p.add_argument(
        "--prose", action="store_true",
        help="add an LLM-drafted orientation paragraph above the scanned facts "
             "(opt-in; needs ANTHROPIC_API_KEY; facts stay deterministic)",
    )
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("mark", help="attest a doc is accurate at HEAD (human-owned docs)")
    p.add_argument("docs", nargs="+", help="doc names, e.g. read-next decisions")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("verify", help="verification score (0.00-1.00) per doc")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("read", help="print the first-read path for an AI session")
    p.add_argument("--paths", action="store_true", help="print file paths only")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("diff", help="what changed vs. what each doc claims (+ sync preview)")
    p.add_argument("docs", nargs="*", help="doc names (default: every doc that isn't fresh)")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("watches", help="show watch globs and propose additions")
    p.add_argument("docs", nargs="*", help="doc names (default: all)")
    p.add_argument("--apply", action="store_true", help="write proposed watches into the docs")
    p.set_defaults(func=cmd_watches)

    p = sub.add_parser("hook", help="manage the pre-push freshness gate")
    p.add_argument("action", choices=["install", "uninstall"])
    p.add_argument("--force", action="store_true", help="overwrite a non-slate pre-push hook")
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("fleet", help="freshness roll-up across multiple repos")
    p.add_argument(
        "paths", nargs="*",
        help="repo paths, or parent dirs to scan one level deep (default: cwd's children)",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--ci", action="store_true", help="exit 1 if any repo has problems")
    p.set_defaults(func=cmd_fleet, needs_repo=False)
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
    scan = scanner.scan(root)
    written = generator.generate_all(scan, force=args.force)
    print(f"initialized context layer at {gitutil.head_commit(root) or '(no commits yet)'}:")
    for path in written:
        print(f"  wrote {path}")
    print("\nnext: fill in the (human) sections, then commit the context layer.")
    return 0


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

    scan = scanner.scan(root)
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
    skipped = [d.spec.name for d in docs if d not in selected and not d.spec.generated]
    if not args.docs and skipped:
        print(f"human-owned docs untouched ({', '.join(skipped)}) — review and `slate mark` them")
    return 0


def cmd_mark(root: Path, args: argparse.Namespace) -> int:
    docs = context.load_all(root)
    selected = _select(docs, args.docs)
    if selected is None:
        return 2
    commit = gitutil.head_commit(root)
    for doc in selected:
        context.stamp(doc, commit)
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
            }
            for v in results
        ], indent=2))
        return 0
    width = max(len(v.rel_path) for v in results) + 2
    for v in results:
        icon = STATUS_ICONS[v.report.status]
        bar = _bar(v.score)
        print(f"{icon} {v.rel_path:<{width}} {v.score:.2f} {bar}")
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
    if args.paths:
        for spec in ordered:
            print(spec.rel_path)
        return 0
    print("first-read path (read in order; trust per status):\n")
    for i, spec in enumerate(ordered, 1):
        r = reports[spec.name]
        icon = STATUS_ICONS[r.status]
        print(f"{i}. {icon} {spec.rel_path} [{r.status}] — {spec.title}")
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


def cmd_fleet(_root: Path | None, args: argparse.Namespace) -> int:
    roots = _fleet_roots([Path(p) for p in args.paths] or [Path.cwd()])
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


def _fleet_roots(paths: list[Path]) -> list[Path]:
    """Each arg is a repo, or a parent whose immediate children are checked."""
    roots: list[Path] = []
    for path in paths:
        path = path.resolve()
        if (path / ".git").exists():
            roots.append(path)
            continue
        if path.is_dir():
            roots.extend(sorted(
                child for child in path.iterdir()
                if child.is_dir() and (child / ".git").exists()
            ))
    return roots


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


if __name__ == "__main__":
    sys.exit(main())
