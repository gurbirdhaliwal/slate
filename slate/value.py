"""The value ledger — measured evidence of what Slate is saving you.

Every run of the core commands leaves a one-line receipt (and ``slate value``
shows the running total): how many tokens of trusted context were served
instead of re-exploring the repo, how many stale docs were caught before an
agent trusted them, and what the deterministic syncs cost (0 tokens) versus
the manual "ask the AI to rewrite the docs" workflow.

Honesty rules (the same contract as ``benchmarks/benchmark.py``):

  MEASURED   — everything stored in the ledger: real file sizes from the
               working tree, real command events, real wall-clock timings.
  ESTIMATED  — dollar/token conversions happen only at display time, under
               stated assumptions (chars/4 tokenization, published list
               prices). Estimates are arithmetic over measured sizes — never
               invented, never stored as fact.

The ledger lives at ``.git/slate/value.json`` — per-clone, never committed,
and invisible to the freshness engine (recording value must never stale a
doc). None of this feeds trust math; a ledger failure must never break a
command, so every public entry point is best-effort.
"""

from __future__ import annotations

import functools
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import context, gitutil, scanner
from .context import CONTEXT_DOC_PATHS, DOC_SPECS, FRESH

# Kept in lockstep with benchmarks/benchmark.py so every surface quotes the
# same assumptions. 4 chars/token; Claude Sonnet list price (mid-2026).
CHARS_PER_TOKEN = 4
PRICE_IN = 3.00   # USD per million input tokens
PRICE_OUT = 15.00  # USD per million output tokens

BASELINE_NOTE = (
    "baseline = measured sizes of what a disciplined agent re-reads without a "
    "context layer: the file listing, build manifests, entry-point files, and "
    "the 5 largest source files"
)

_TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".c",
    ".h", ".cpp", ".cs", ".sh", ".sql", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".json", ".cfg", ".ini", ".html", ".css", ".xml",
}

_MANIFESTS = ("README.md", "Makefile", "pyproject.toml", "package.json", "pom.xml")

_SEEN_CAP = 500  # catch-dedupe keys kept; oldest dropped first


def enabled() -> bool:
    return not os.environ.get("SLATE_NO_VALUE")


def _best_effort(fn):
    """Value tracking is a receipt, not a feature gate — never break the command."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not enabled():
            return None
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None
    return wrapper


def tokens(chars: int) -> int:
    return chars // CHARS_PER_TOKEN


def cost_in(tok: int) -> float:
    return tok / 1_000_000 * PRICE_IN


def cost_out(tok: int) -> float:
    return tok / 1_000_000 * PRICE_OUT


# --- ledger I/O --------------------------------------------------------------

def ledger_path(root: Path) -> Path:
    return gitutil.state_dir(root) / "value.json"


def _empty_ledger() -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "sessions": {"count": 0, "context_tokens": 0, "baseline_tokens": 0},
        "syncs": {"count": 0, "healed_docs": 0, "measured_ms": 0.0,
                  "manual_input_tokens": 0, "manual_output_tokens": 0},
        "catches": {"count": 0, "seen": []},
        "repairs": {"verified": 0, "refused": 0},
    }


def _load(root: Path) -> dict:
    try:
        data = json.loads(ledger_path(root).read_text())
    except (OSError, json.JSONDecodeError):
        return _empty_ledger()
    if not isinstance(data, dict) or data.get("version") != 1:
        return _empty_ledger()
    # Missing sections (older/hand-edited ledgers) heal to empty rather than crash.
    empty = _empty_ledger()
    for key in ("sessions", "syncs", "catches", "repairs"):
        section = data.get(key)
        data[key] = {**empty[key], **section} if isinstance(section, dict) else empty[key]
    return data


def _save(root: Path, data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


# --- measurement (all sizes read from the real working tree) -----------------

def measure_session(root: Path) -> dict | None:
    """Measured size of the context layer vs. the exploration baseline.

    Byte sizes are used as a character proxy (the token heuristic is chars/4
    anyway); every number comes from files that exist right now.
    """
    layer_chars = sum(
        _size(spec.path(root)) for spec in DOC_SPECS if spec.path(root).exists()
    )
    if layer_chars == 0:
        return None  # no context layer — nothing is being served

    tracked = gitutil.list_files(root)
    sizes: dict[str, int] = {}
    for p in tracked:
        if Path(p).suffix.lower() in _TEXT_SUFFIXES and p not in CONTEXT_DOC_PATHS:
            n = _size(root / p)
            if n:
                sizes[p] = n

    scan = scanner.scan(root)
    manifests = [p for p in _MANIFESTS if p in sizes]
    entry_hints = [h for m in scan.modules for h in m.entry_hints if h in sizes]
    code_sizes = {p: n for p, n in sizes.items()
                  if Path(p).suffix.lower() not in (".md", ".txt")}
    largest = sorted(code_sizes, key=code_sizes.get, reverse=True)[:5]
    exploration = list(dict.fromkeys(manifests + entry_hints + largest))
    listing_chars = sum(len(p) + 1 for p in tracked)
    baseline_chars = listing_chars + sum(sizes[p] for p in exploration)

    return {
        "context_tokens": tokens(layer_chars),
        "baseline_tokens": tokens(baseline_chars),
        "baseline_files": len(exploration),
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# --- event recording ---------------------------------------------------------

@_best_effort
def record_session(root: Path) -> dict | None:
    """One agent/human session started from the context layer (a `read`)."""
    measured = measure_session(root)
    if measured is None:
        return None
    data = _load(root)
    data["sessions"]["count"] += 1
    data["sessions"]["context_tokens"] += measured["context_tokens"]
    data["sessions"]["baseline_tokens"] += measured["baseline_tokens"]
    _save(root, data)
    return measured


@_best_effort
def record_catches(root: Path, reports) -> tuple[int, int] | None:
    """Count non-fresh docs surfaced before anyone acted on them.

    Deduped per (doc, sync anchor): re-running `slate status` on the same
    staleness is one catch, not many — the count only grows when Slate
    catches something new.
    """
    data = _load(root)
    new = _fold_catches(data, reports)
    if new:
        _save(root, data)
    return new, data["catches"]["count"]


def _fold_catches(data: dict, reports) -> int:
    seen = data["catches"]["seen"]
    new = 0
    for r in reports:
        if r.status == FRESH:
            continue
        key = f"{r.doc.spec.name}@{r.doc.synced_commit or 'none'}"
        if key in seen:
            continue
        seen.append(key)
        new += 1
    if new:
        data["catches"]["count"] += new
        del seen[:-_SEEN_CAP]
    return new


@_best_effort
def sync_baseline(root: Path, reports: dict, selected_names: list[str]) -> dict | None:
    """Measured *before* a sync: what the manual AI-rewrite workflow would read.

    Mirrors the benchmark's maintenance replay: the model would re-read the
    whole doc layer plus the changed watched files (input) and rewrite the
    non-fresh docs (output). Only docs that are actually non-fresh count —
    a pure re-anchor of fresh docs saves nothing and is recorded as nothing.
    """
    healed = [reports[n] for n in selected_names
              if n in reports and reports[n].status != FRESH]
    if not healed:
        return {"healed": [], "manual_input_tokens": 0, "manual_output_tokens": 0}
    layer_chars = sum(
        _size(spec.path(root)) for spec in DOC_SPECS if spec.path(root).exists()
    )
    changed = sorted({p for r in healed for p in r.changed_watched})
    changed_chars = sum(_size(root / p) for p in changed)  # deleted files → 0
    healed_chars = sum(_size(r.doc.spec.path(root)) for r in healed)
    return {
        "healed": [r.doc.spec.name for r in healed],
        "manual_input_tokens": tokens(layer_chars + changed_chars),
        "manual_output_tokens": tokens(healed_chars),
        "_reports": healed,
    }


@_best_effort
def record_sync(root: Path, baseline: dict | None, elapsed_ms: float) -> dict | None:
    """One deterministic sync ran (0 tokens, measured wall-clock)."""
    if baseline is None:
        return None
    data = _load(root)
    data["syncs"]["count"] += 1
    data["syncs"]["healed_docs"] += len(baseline["healed"])
    data["syncs"]["measured_ms"] = round(data["syncs"]["measured_ms"] + elapsed_ms, 1)
    data["syncs"]["manual_input_tokens"] += baseline["manual_input_tokens"]
    data["syncs"]["manual_output_tokens"] += baseline["manual_output_tokens"]
    # Healing a stale doc implies catching it, even if `status` was never run.
    _fold_catches(data, baseline.get("_reports", []))
    _save(root, data)
    return {
        "healed": baseline["healed"],
        "manual_input_tokens": baseline["manual_input_tokens"],
        "manual_output_tokens": baseline["manual_output_tokens"],
        "elapsed_ms": round(elapsed_ms, 1),
    }


class timer:
    """Tiny context manager: `with value.timer() as t: ...; t.ms`."""

    def __enter__(self) -> "timer":
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000


# --- totals + rendering ------------------------------------------------------

# --- repairs -----------------------------------------------------------------
# What this counts, and what it deliberately does not.
#
# The plan for this phase asked for "sessions that started fresh *because* a
# prior session repaired them". That number is not available honestly. Phase 4
# measured the counterfactual directly and it does not hold: a control with no
# repair loop at all converged its layer in 36% of trials in one sweep and 69%
# in another, by the agent rewriting the docs by hand. Attributing a fresh
# session to repair would credit the loop for something that happens anyway
# between a third and two thirds of the time.
#
# So the ledger records the two things that *are* facts about what the gate did:
#
#   verified  a rewrite that passed `repair.verify_repair` and was written.
#   refused   a rewrite the gate rejected, so it never landed. This is the
#             causally clean one — the edit did not happen *because* the check
#             said no, and there is no counterfactual to argue about.
#
# Neither is a claim that the layer would have rotted otherwise.


@_best_effort
def record_repair(root: Path, outcome: str) -> dict | None:
    """Note one pass through the repair gate. Best-effort, like everything here."""
    from .repair import REJECTED, REPAIRED

    if outcome not in (REPAIRED, REJECTED):
        return None  # `unchanged` is a correct decline, not a gate event
    data = _load(root)
    key = "verified" if outcome == REPAIRED else "refused"
    data["repairs"][key] += 1
    _save(root, data)
    return dict(data["repairs"])


def repair_footer(event: dict | None) -> str | None:
    if not event:
        return None
    verified, refused = event["verified"], event["refused"]
    if refused:
        return (f"value: {verified} verified repair(s), {refused} refused "
                f"before landing — all-time in this clone")
    return f"value: {verified} verified repair(s) all-time in this clone"


def totals(root: Path) -> dict:
    """Cumulative ledger, split into measured facts and labeled estimates."""
    data = _load(root)
    s, y, c, r = (data["sessions"], data["syncs"], data["catches"],
                  data["repairs"])
    session_delta = s["baseline_tokens"] - s["context_tokens"]
    session_usd = cost_in(session_delta)
    maint_usd = cost_in(y["manual_input_tokens"]) + cost_out(y["manual_output_tokens"])
    return {
        "measured": {
            "sessions_served": s["count"],
            "context_tokens_served": s["context_tokens"],
            "exploration_baseline_tokens": s["baseline_tokens"],
            "stale_docs_caught": c["count"],
            "syncs_run": y["count"],
            "stale_docs_healed": y["healed_docs"],
            "sync_wall_clock_ms": y["measured_ms"],
            "sync_tokens_spent": 0,
            "repairs_verified": r["verified"],
            "repairs_refused": r["refused"],
        },
        "estimated": {
            "session_input_tokens_avoided": session_delta,
            "session_cost_avoided_usd": round(session_usd, 4),
            "maintenance_input_tokens_avoided": y["manual_input_tokens"],
            "maintenance_output_tokens_avoided": y["manual_output_tokens"],
            "maintenance_cost_avoided_usd": round(maint_usd, 4),
            "total_cost_avoided_usd": round(session_usd + maint_usd, 4),
        },
        "assumptions": {
            "chars_per_token": CHARS_PER_TOKEN,
            "price_per_mtok_in_usd": PRICE_IN,
            "price_per_mtok_out_usd": PRICE_OUT,
            "baseline": BASELINE_NOTE,
            "ledger": str(ledger_path(root)),
        },
    }


def session_footer(measured: dict | None) -> str | None:
    """One-line receipt for `slate read` — measured sizes only."""
    if not measured:
        return None
    ctx, base = measured["context_tokens"], measured["baseline_tokens"]
    if base > ctx:
        return (
            f"value: served {ctx:,} tokens of trusted context — re-exploring "
            f"measures {base:,} tokens ({measured['baseline_files']} files + tree); "
            f"~{base - ctx:,} input tokens avoided · totals: `slate value`"
        )
    # Small repos: the fixed-size layer can exceed the baseline. Say so.
    return (
        f"value: context layer is {ctx:,} tokens vs {base:,} to re-explore this "
        f"repo — session-start savings grow with repo size (`slate value`)"
    )


def sync_footer(event: dict | None) -> str | None:
    if not event or not event["healed"]:
        return None
    est = cost_in(event["manual_input_tokens"]) + cost_out(event["manual_output_tokens"])
    docs = ", ".join(event["healed"])
    return (
        f"value: healed {len(event['healed'])} stale doc(s) ({docs}) in "
        f"{event['elapsed_ms']:.0f} ms, 0 tokens — a manual AI rewrite measures "
        f"~{event['manual_input_tokens']:,} in + ~{event['manual_output_tokens']:,} out "
        f"tokens (≈${est:.2f} at list price)"
    )


def catches_footer(result: tuple[int, int] | None) -> str | None:
    if not result:
        return None
    new, total = result
    if not new:
        return None
    noun = "doc" if new == 1 else "docs"
    return (
        f"value: caught {new} stale {noun} before an agent trusted "
        f"{'it' if new == 1 else 'them'} — {total} catch(es) all-time in this clone"
    )


def render_report(t: dict) -> str:
    m, e, a = t["measured"], t["estimated"], t["assumptions"]
    lines = [
        "slate value — what this repo's context layer has saved (clone-local ledger)",
        "",
        "measured (real events, real file sizes, real wall-clock):",
        f"  sessions served from the context layer   {m['sessions_served']:,}",
        f"  context tokens served                    {m['context_tokens_served']:,}",
        f"  stale docs caught before use             {m['stale_docs_caught']:,}",
        f"  deterministic syncs run                  {m['syncs_run']:,} "
        f"({m['stale_docs_healed']:,} stale doc(s) healed in "
        f"{m['sync_wall_clock_ms']:.0f} ms total, {m['sync_tokens_spent']} tokens)",
        f"  claim repairs verified and written       {m['repairs_verified']:,}",
        f"  claim repairs refused before landing     {m['repairs_refused']:,}",
        "",
        "estimated — arithmetic over the measured sizes above, at the stated assumptions:",
        f"  session-start input tokens avoided       ~{e['session_input_tokens_avoided']:,}"
        f"  (~${e['session_cost_avoided_usd']:.4f})",
        f"  maintenance tokens avoided               ~{e['maintenance_input_tokens_avoided']:,} in"
        f" + ~{e['maintenance_output_tokens_avoided']:,} out"
        f"  (~${e['maintenance_cost_avoided_usd']:.4f})",
        f"  total estimated spend avoided            ~${e['total_cost_avoided_usd']:.4f}",
        "",
        "evidence & assumptions:",
        f"  · {a['baseline']}",
        f"  · {a['chars_per_token']} chars/token; ${a['price_per_mtok_in_usd']}/M input, "
        f"${a['price_per_mtok_out_usd']}/M output tokens (Claude Sonnet list price)",
        "  · stale catches are deduped per (doc, sync anchor) — re-checking the same",
        "    staleness never inflates the count",
        "  · repairs count passes through the verification gate, not layer freshness.",
        "    A measured control with no repair loop converged its own layer in 36-69%",
        "    of trials, so 'the docs are fresh' is not credited to repair here",
        "    (benchmarks/agentbench/E3-RESULTS.md)",
        f"  · ledger: {a['ledger']} (per-clone; delete it to reset)",
        "  · deep-dive on this methodology: python benchmarks/benchmark.py",
    ]
    if m["sessions_served"] and e["session_input_tokens_avoided"] < 0:
        lines.insert(
            10,
            "  (negative: on a small repo the fixed-size layer can exceed the\n"
            "   exploration baseline — the session-start advantage scales with repo size)",
        )
    return "\n".join(lines)
