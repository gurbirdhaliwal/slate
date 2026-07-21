"""Doc generation — turns a RepoScan into the Markdown context layer.

Generated content is deterministic (same repo state → same bytes, modulo
timestamps) so that `slate sync` diffs are reviewable like any other code
change. Prose sections are scaffolded once with clearly-marked human slots;
sync never touches anything outside the auto-block.
"""

from __future__ import annotations

from . import context, gitutil
from .context import AUTO_BEGIN, AUTO_END, DOC_SPECS, SLATE_DIR, ContextDoc, DocSpec
from .scanner import RepoScan


def generate_all(scan: RepoScan, *, force: bool = False) -> list[str]:
    """Create the full context layer. Returns the rel paths written.

    Existing docs are left alone unless ``force`` — init must never eat a
    human-maintained context layer by accident.
    """
    root = scan.root
    commit = gitutil.head_commit(root)
    written: list[str] = []
    for spec in DOC_SPECS:
        path = spec.path(root)
        if path.exists() and not force:
            continue
        doc = ContextDoc(spec, {}, _initial_body(spec, scan))
        if spec.generated:
            doc.body = context.replace_auto_block(doc.body, auto_content(spec, scan))
        # Watches must exist before stamping — the stamp digests the watched files.
        doc.meta["slate_watches"] = context.default_watches(spec, scan)
        context.stamp(root, doc, commit)
        context.save(root, doc)
        written.append(spec.rel_path)
    return written


def sync_doc(doc: ContextDoc, scan: RepoScan, prose=None) -> None:
    """Regenerate the auto-block and re-anchor freshness to current HEAD.

    ``prose`` is an optional callable ``(spec, facts_markdown) -> str`` that
    returns an orientation block to place above the scanned facts (the
    Phase 2 LLM hook). It may only *add* prose — the deterministic facts are
    always present and always come from the scan.
    """
    if doc.spec.generated:
        block = auto_content(doc.spec, scan)
        if prose is not None:
            block = prose(doc.spec, block).strip() + "\n\n" + block
        doc.body = context.replace_auto_block(doc.body, block)
    context.stamp(scan.root, doc, gitutil.head_commit(scan.root))
    context.save(scan.root, doc)


# --- per-doc content -------------------------------------------------------

def _initial_body(spec: DocSpec, scan: RepoScan) -> str:
    name = scan.readme_title or scan.root.name
    if spec.name == "agents":
        return _agents_shell(name)
    if spec.name == "architecture":
        return (
            "# Architecture\n\n"
            f"{AUTO_BEGIN}\n{AUTO_END}\n\n"
            "## System overview (human)\n\n"
            "_Describe what the system does and the one or two invariants an\n"
            "AI must not break. Keep it under a screen._\n\n"
            "## Boundaries (human)\n\n"
            "_What each part may and may not know about the others._\n"
        )
    if spec.name == "modules":
        return f"# Module map\n\n{AUTO_BEGIN}\n{AUTO_END}\n\n## Notes (human)\n"
    if spec.name == "workflows":
        return (
            "# Workflows\n\nHow to build, test, and run this repo.\n\n"
            f"{AUTO_BEGIN}\n{AUTO_END}\n\n## Gotchas (human)\n"
        )
    if spec.name == "decisions":
        return (
            "# Decision log\n\n"
            "Append-only. One entry per decision that a future reader (or AI)\n"
            "would otherwise re-litigate.\n\n"
            "```\nDate: YYYY-MM-DD\nDecision:\nRationale:\nTrade-off:\nRevisit trigger:\n```\n"
        )
    if spec.name == "read-next":
        return (
            "# Read next — current focus\n\n"
            "The smallest useful context for the *current* task. Rewrite this\n"
            "when the focus changes; run `slate mark read-next` after.\n\n"
            "## Current focus\n\n_Nothing in flight._\n\n"
            "## Landmines\n\n_None recorded._\n"
        )
    raise ValueError(f"unknown doc: {spec.name}")


def _agents_shell(project: str) -> str:
    return (
        f"# AGENTS.md — start here\n\n"
        f"Repo context for **{project}** is maintained by [Slate](https://github.com/gurbirdhaliwal/slate).\n"
        f"Read the docs below **in order** before writing or changing code, and\n"
        f"trust them only as far as their freshness status allows.\n\n"
        f"{AUTO_BEGIN}\n{AUTO_END}\n\n"
        "## Trust protocol\n\n"
        "- If the `slate` MCP server is available, prefer its tools: `slate_read`\n"
        "  (session start), `slate_status` / `slate_diff` (mid-task), and — when\n"
        "  write access is granted — `slate_sync`, `slate_update_focus`,\n"
        "  `slate_append_decision` (session end). The CLI commands below are the\n"
        "  fallback.\n"
        "- Run `slate status` first. `fresh` docs are safe to rely on.\n"
        "- `stale` means watched code changed since the doc was synced — verify\n"
        "  against the code before acting, or run `slate sync`.\n"
        "- `needs-verification` means the freshness anchor is gone and the\n"
        "  content could not be verified against the last sync — treat the doc\n"
        "  as a rumor.\n"
        "- After completing a task: update `.slate/read-next.md`, append to\n"
        "  `.slate/decisions.md` if you made a call worth recording, then run\n"
        "  `slate sync`.\n\n"
        "## Extra instructions (human)\n"
    )


def auto_content(spec: DocSpec, scan: RepoScan) -> str:
    """The deterministic auto-block content for a doc (public: diffs previews it)."""
    if spec.name == "agents":
        return _agents_auto(scan)
    if spec.name == "architecture":
        return _architecture_auto(scan)
    if spec.name == "modules":
        return _modules_auto(scan)
    if spec.name == "workflows":
        return _workflows_auto(scan)
    return ""


def _agents_auto(scan: RepoScan) -> str:
    ordered = sorted((s for s in DOC_SPECS if s.read_order), key=lambda s: s.read_order)
    lines = ["## Read order", ""]
    descriptions = {
        "agents": "this file — routing and trust protocol",
        "read-next": "current focus: what is in flight right now",
        "architecture": "what the system is and its invariants",
        "modules": "where things live",
        "workflows": "how to build, test, and run",
        "decisions": "why things are the way they are",
    }
    step = 1
    for s in ordered:
        if s.name == "agents":
            continue
        lines.append(f"{step}. [`{s.rel_path}`]({s.rel_path}) — {descriptions[s.name]}")
        step += 1
    return "\n".join(lines)


def _architecture_auto(scan: RepoScan) -> str:
    lines = ["## Shape of the repo (scanned)", ""]
    total = len(scan.files)
    langs = ", ".join(f"{lang} ({n})" for lang, n in scan.languages.most_common(5))
    lines.append(f"- {total} files; code languages: {langs or 'none detected'}")
    if scan.ci_workflows:
        lines.append(f"- CI workflows: {', '.join(scan.ci_workflows)}")
    for module in scan.modules:
        if module.name == ".":
            continue
        hint = f" — entry points: {', '.join(f'`{h}`' for h in module.entry_hints)}" if module.entry_hints else ""
        lines.append(
            f"- `{module.name}/` — {module.file_count} files"
            + (f", mostly {module.primary_language}" if module.primary_language else "")
            + hint
        )
    lines += ["", "## Module boundaries (scanned)", ""]
    lines += _edge_lines(scan.edges)
    return "\n".join(lines)


def _edge_lines(edges: dict[str, set[str]]) -> list[str]:
    """Dependency edges as a tracked fact — one line per module that imports.

    Deterministic by construction: sources and targets are both sorted, so the
    same graph always renders byte-identical (a flaky fact would manufacture
    false `stale`). Top-level-dir granularity only, matching the shallow,
    resolver-free import graph — no false precision.
    """
    out: list[str] = []
    for source in sorted(edges):
        targets = sorted(edges[source])
        if targets:
            out.append(f"- `{source}/` → " + ", ".join(f"`{t}/`" for t in targets))
    return out or ["- _no cross-module imports detected_"]


def _modules_auto(scan: RepoScan) -> str:
    lines = [
        "| Module | Files | Primary language | Entry hints |",
        "|--------|-------|------------------|-------------|",
    ]
    for module in scan.modules:
        hints = ", ".join(f"`{h}`" for h in module.entry_hints) or "—"
        lang = module.primary_language or "—"
        name = f"`{module.name}/`" if module.name != "." else "*(repo root)*"
        lines.append(f"| {name} | {module.file_count} | {lang} | {hints} |")
    return "\n".join(lines)


def _workflows_auto(scan: RepoScan) -> str:
    if not scan.commands and not scan.ci_workflows:
        return "_No build/test commands detected._"
    lines: list[str] = []
    for tool, invocations in scan.commands.items():
        lines.append(f"**{tool}**")
        lines.extend(f"- `{c}`" for c in invocations)
        lines.append("")
    if scan.ci_workflows:
        lines.append("**CI**")
        lines.extend(f"- `.github/workflows/{w}.yml`" for w in scan.ci_workflows)
    return "\n".join(lines).strip()
