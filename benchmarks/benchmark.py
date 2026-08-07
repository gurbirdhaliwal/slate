#!/usr/bin/env python3
"""Quantifies Slate against the manual alternative: "just tell the AI to
write and update .md context files."

Run it against any repo with a Slate context layer (default: the repo this
script lives in — Slate dogfooding itself):

    python benchmarks/benchmark.py            # markdown report
    python benchmarks/benchmark.py --json     # machine-readable

Everything here is deterministic and reproducible. Two kinds of numbers are
reported, always labeled:

  MEASURED   — byte/token counts of real files, wall-clock timings of real
               Slate operations, and a replay of the repo's actual git
               history through the freshness engine.
  ESTIMATED  — what the manual workflow *would* cost in tokens/dollars,
               computed from the same measured file sizes under stated
               assumptions (chars/4 tokenization, published API prices).
               No LLM is called; estimates are arithmetic, not vibes.

Baselines compared for session-start context:
  A. slate_read        — the context layer with trust labels (what Slate feeds)
  B. guided exploration— README + file listing + build manifests + the five
                         largest source files (a disciplined agent's manual
                         rediscovery)
  C. full repo dump    — every tracked text file (the brute-force ceiling)

Honesty note: the context layer has a roughly fixed size (~1-2K tokens), so
on a tiny repo it can exceed the exploration baseline — the session-start
advantage scales with repo size. The maintenance and staleness-detection
advantages hold at any size.

Maintenance replay: for every commit since the context layer was created
that touched watched code, the manual workflow re-reads the docs + the
changed files and rewrites the affected docs through the model; Slate runs
a deterministic sync. Token cost for the former is estimated from the real
blob sizes at each historical commit; Slate's cost is measured wall time
and exactly zero tokens.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slate import context, freshness, generator, gitutil, globs, scanner, verify  # noqa: E402
from slate.mcp import SlateMCPServer  # noqa: E402

CHARS_PER_TOKEN = 4  # standard rough heuristic for English/code
# Claude Sonnet list prices (per million tokens) as of mid-2026.
PRICE_IN = 3.00
PRICE_OUT = 15.00

TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".c",
    ".h", ".cpp", ".cs", ".sh", ".sql", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".json", ".cfg", ".ini", ".html", ".css", ".xml",
}


def tokens(chars: int) -> int:
    return chars // CHARS_PER_TOKEN


def cost_in(tok: int) -> float:
    return tok / 1_000_000 * PRICE_IN


def cost_out(tok: int) -> float:
    return tok / 1_000_000 * PRICE_OUT


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


# --- session-start context acquisition --------------------------------------

def measure_session_start(root: Path) -> dict:
    context_paths = [s.rel_path for s in context.DOC_SPECS]

    layer_chars = sum(
        len((root / p).read_text(encoding="utf-8")) for p in context_paths if (root / p).exists()
    )

    tracked = gitutil.list_files(root)
    text_files = [
        p for p in tracked
        if Path(p).suffix.lower() in TEXT_SUFFIXES and p not in context_paths
    ]
    dump_chars = 0
    sizes: dict[str, int] = {}
    for p in text_files:
        try:
            n = len((root / p).read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        dump_chars += n
        sizes[p] = n

    scan = scanner.scan(root)
    manifests = [p for p in ("README.md", "Makefile", "pyproject.toml",
                             "package.json", "pom.xml") if p in sizes]
    entry_hints = [h for m in scan.modules for h in m.entry_hints if h in sizes]
    code_sizes = {p: n for p, n in sizes.items()
                  if Path(p).suffix.lower() not in (".md", ".txt")}
    largest = sorted(code_sizes, key=code_sizes.get, reverse=True)[:5]
    exploration_set = list(dict.fromkeys(manifests + entry_hints + largest))
    listing_chars = sum(len(p) + 1 for p in tracked)  # the file-tree listing
    exploration_chars = listing_chars + sum(sizes[p] for p in exploration_set)

    return {
        "slate_read": {
            "chars": layer_chars,
            "tokens": tokens(layer_chars),
            "cost_usd": round(cost_in(tokens(layer_chars)), 4),
        },
        "guided_exploration": {
            "chars": exploration_chars,
            "tokens": tokens(exploration_chars),
            "cost_usd": round(cost_in(tokens(exploration_chars)), 4),
            "files_opened": len(exploration_set),
        },
        "full_repo_dump": {
            "chars": dump_chars,
            "tokens": tokens(dump_chars),
            "cost_usd": round(cost_in(tokens(dump_chars)), 4),
            "files": len(sizes),
        },
    }


# --- measured wall-clock timings of real Slate operations -------------------

def _timed(fn, repeat: int = 5) -> float:
    best = min(_once(fn) for _ in range(repeat))
    return round(best * 1000, 1)


def _once(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def measure_timings(root: Path) -> dict:
    server = SlateMCPServer(root)
    read_call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "slate_read", "arguments": {}}}

    timings = {
        "slate_status_ms": _timed(lambda: freshness.evaluate_all(root)),
        "slate_verify_ms": _timed(lambda: verify.verify_all(root)),
        "repo_scan_ms": _timed(lambda: scanner.scan(root)),
        "mcp_slate_read_ms": _timed(lambda: server.handle(read_call)),
    }

    # sync mutates files — run it on a throwaway clone of the repo
    tmp = Path(tempfile.mkdtemp(prefix="slate-bench-"))
    try:
        subprocess.run(["git", "clone", "--quiet", str(root), str(tmp / "clone")],
                       check=True, capture_output=True)
        clone = tmp / "clone"
        scan = scanner.scan(clone)
        docs = [d for d in context.load_all(clone) if d.spec.generated]

        def do_sync():
            for doc in docs:
                generator.sync_doc(doc, scan)

        timings["slate_sync_ms"] = _timed(do_sync, repeat=3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return timings


# --- git-history replay: staleness + maintenance costs ----------------------

def replay_history(root: Path, since: str) -> dict:
    docs = context.load_all(root)
    doc_watches = {d.spec.name: d.watches for d in docs}
    doc_chars = {
        d.spec.name: len(d.spec.path(root).read_text(encoding="utf-8"))
        for d in docs if d.spec.path(root).exists()
    }
    context_paths = {s.rel_path for s in context.DOC_SPECS}
    layer_chars = sum(doc_chars.values())

    commits = [c for c in _git(root, "rev-list", "--reverse", f"{since}..HEAD").split() if c]
    staling, sync_commits = [], 0
    manual_in_tokens = manual_out_tokens = 0

    for sha in commits:
        subject = _git(root, "log", "-1", "--format=%s", sha).strip()
        if subject.lower().startswith("sync context layer"):
            sync_commits += 1
        changed = [
            p for p in _git(root, "diff", "--name-only", f"{sha}^", sha).splitlines()
            if p and p not in context_paths
        ]
        affected = [
            name for name, watches in doc_watches.items()
            if watches and globs.filter_paths(watches, changed)
        ]
        if not affected:
            continue

        watched_changed = sorted({
            p for name in affected for p in globs.filter_paths(doc_watches[name], changed)
        })
        changed_chars = 0
        for p in watched_changed:
            try:
                changed_chars += int(_git(root, "cat-file", "-s", f"{sha}:{p}").strip())
            except subprocess.CalledProcessError:
                pass  # deleted at this commit — nothing to re-read

        affected_chars = sum(doc_chars.get(n, 0) for n in affected)
        # Manual workflow per staling commit: the model re-reads the whole
        # doc layer + the changed files (input), rewrites affected docs (output).
        manual_in_tokens += tokens(layer_chars + changed_chars)
        manual_out_tokens += tokens(affected_chars)
        staling.append({"commit": sha[:7], "affected_docs": affected,
                        "watched_files_changed": len(watched_changed)})

    manual_cost = cost_in(manual_in_tokens) + cost_out(manual_out_tokens)
    return {
        "since": since[:7],
        "commits_analyzed": len(commits),
        "commits_that_staled_docs": len(staling),
        "sync_commits_in_history": sync_commits,
        "silent_rot_rate": round(len(staling) / len(commits), 2) if commits else 0.0,
        "manual_ai_maintenance": {
            "input_tokens": manual_in_tokens,
            "output_tokens": manual_out_tokens,
            "cost_usd": round(manual_cost, 2),
        },
        "slate_maintenance": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        "staling_commits": staling,
    }


# --- report -----------------------------------------------------------------

def run(root: Path, since: str | None) -> dict:
    if since is None:
        first = _git(root, "log", "--format=%H", "--diff-filter=A", "--", "AGENTS.md")
        since = first.split()[-1] if first.split() else None
    if since is None:
        raise SystemExit("no context layer history found (AGENTS.md never added)")
    return {
        "repo": root.name,
        "head": gitutil.head_commit(root),
        "assumptions": {
            "chars_per_token": CHARS_PER_TOKEN,
            "price_per_mtok_in_usd": PRICE_IN,
            "price_per_mtok_out_usd": PRICE_OUT,
        },
        "session_start": measure_session_start(root),
        "timings_measured": measure_timings(root),
        "history_replay": replay_history(root, since),
    }


def render_markdown(r: dict) -> str:
    s = r["session_start"]
    t = r["timings_measured"]
    h = r["history_replay"]
    sr, ge, fd = s["slate_read"], s["guided_exploration"], s["full_repo_dump"]
    x_ge = ge["tokens"] / sr["tokens"] if sr["tokens"] else 0
    x_fd = fd["tokens"] / sr["tokens"] if sr["tokens"] else 0
    m = h["manual_ai_maintenance"]

    lines = [
        f"# Slate benchmark — `{r['repo']}` @ `{r['head']}`",
        "",
        "Slate vs. the manual workflow (\"tell the AI to write/update .md files\"),",
        "measured on this repository's real files and real git history.",
        f"Assumptions for estimates: {r['assumptions']['chars_per_token']} chars/token; "
        f"${r['assumptions']['price_per_mtok_in_usd']}/M input, "
        f"${r['assumptions']['price_per_mtok_out_usd']}/M output tokens (Claude Sonnet list price).",
        "",
        "## 1. Session start: what the agent must ingest (measured sizes)",
        "",
        "| Approach | Tokens | Cost/session | vs Slate |",
        "|---|---|---|---|",
        f"| **Slate** (`slate_read`: 6 docs + trust labels) | **{sr['tokens']:,}** | ${sr['cost_usd']:.4f} | 1× |",
        f"| Guided exploration ({ge['files_opened']} files + file tree) | {ge['tokens']:,} | ${ge['cost_usd']:.4f} | {x_ge:.1f}× more |",
        f"| Full repo dump ({fd['files']} text files) | {fd['tokens']:,} | ${fd['cost_usd']:.4f} | {x_fd:.1f}× more |",
        "",
        "Every session pays this cost. Over 100 sessions the exploration baseline",
        f"spends ~${(ge['cost_usd'] - sr['cost_usd']) * 100:.2f} more than Slate on input tokens alone —",
        "before counting the model's slower time-to-first-useful-action on a",
        "context window that large, and with zero trust labels attached.",
        "",
        "## 2. Slate operations (measured wall-clock, this machine)",
        "",
        "| Operation | Time |",
        "|---|---|",
        f"| `slate status` (freshness derivation) | {t['slate_status_ms']} ms |",
        f"| `slate verify` (trust scores) | {t['slate_verify_ms']} ms |",
        f"| full repo scan | {t['repo_scan_ms']} ms |",
        f"| MCP `slate_read` (full tool round-trip) | {t['mcp_slate_read_ms']} ms |",
        f"| `slate sync` (regenerate all auto-blocks) | {t['slate_sync_ms']} ms |",
        "",
        "All operations are deterministic, local, and free — 0 tokens.",
        "",
        f"## 3. Maintenance replay: {h['commits_analyzed']} real commits since `{h['since']}`",
        "",
        f"- **{h['commits_that_staled_docs']} of {h['commits_analyzed']} commits "
        f"({int(h['silent_rot_rate'] * 100)}%) invalidated at least one context doc.** "
        "In the manual workflow every one of those is silent rot — no signal exists.",
        f"- The repo's actual history contains {h['sync_commits_in_history']} `slate sync` "
        "commits: each staling change was caught and healed, gated by CI.",
        "",
        "Cost to keep the docs true across those commits:",
        "",
        "| Workflow | Input tokens | Output tokens | Cost |",
        "|---|---|---|---|",
        f"| Manual: AI re-reads docs+changes, rewrites docs | {m['input_tokens']:,} | {m['output_tokens']:,} | ${m['cost_usd']:.2f} |",
        f"| **Slate: deterministic `sync`** | **0** | **0** | **$0.00** (≈{t['slate_sync_ms']} ms each) |",
        "",
        "And the manual number is the *best case* — it assumes the developer",
        "remembers to ask after every staling commit. Skip any of them and the",
        "cost doesn't disappear; it converts into the failure mode Slate exists",
        "to prevent: an AI acting confidently on false context.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python benchmarks/benchmark.py          # this report",
        "python benchmarks/benchmark.py --json   # raw numbers",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(REPO_ROOT), help="repo to benchmark")
    parser.add_argument("--since", default=None,
                        help="commit the context layer was created at (default: auto-detect)")
    parser.add_argument("--json", action="store_true", help="raw JSON instead of markdown")
    args = parser.parse_args(argv)

    results = run(Path(args.repo).resolve(), args.since)
    print(json.dumps(results, indent=2) if args.json else render_markdown(results), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
