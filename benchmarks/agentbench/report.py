#!/usr/bin/env python3
"""Aggregates `runs/*.json` into a report.

    python benchmarks/agentbench/report.py            # markdown to stdout
    python benchmarks/agentbench/report.py --json     # raw aggregate

Reports the median and the full observed range for every metric. Agent runs
are nondeterministic; a single number per arm would be a claim about one
sample, and the spread is the first thing a skeptical reader should be able to
check. Correctness is reported as a fraction of trials, never averaged away.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"

# Records excluded for belonging to an older task revision. Reported rather
# than dropped silently: a reader is entitled to know the directory holds
# results the report refused to use.
SKIPPED: list[dict] = []


def load() -> dict[str, list[dict]]:
    by_arm: dict[str, list[dict]] = {}
    for path in sorted(RUNS.glob("*.json")):
        record = json.loads(path.read_text())
        # Never average two different experiments. A record from an older task
        # revision answers a different question, and `runs/` mixes them freely
        # because a re-run overwrites one arm's files and leaves the rest.
        if record.get("task_revision", 1) != spec.TASK_REVISION:
            SKIPPED.append(record)
            continue
        # When an arm is re-run its records are overwritten in place, so arms
        # in this directory can come from different sweeps on different days.
        # Date the run by its *transcript*, not the sidecar: `--reparse`
        # rewrites every sidecar, which would date them all to the reparse and
        # erase exactly the distinction this is here to preserve.
        stem = path.stem
        transcripts = [RUNS / f"{stem}.jsonl", RUNS / f"{stem}.jsonl.gz"]
        source = next((t for t in transcripts if t.exists()), path)
        # Local time, deliberately: an evening sweep converted to UTC rolls
        # onto the next day and merges two sweeps into one apparent date,
        # erasing the distinction this exists to record.
        record["_ran_at"] = dt.datetime.fromtimestamp(
            source.stat().st_mtime).date().isoformat()
        by_arm.setdefault(record["arm"], []).append(record)
    return by_arm


def provenance(by_arm: dict[str, list[dict]]) -> dict[str, str]:
    """Which day's sweep each arm's records came from."""
    out = {}
    for arm, records in by_arm.items():
        days = sorted({r["_ran_at"] for r in records})
        out[arm] = days[0] if len(days) == 1 else f"{days[0]}–{days[-1]}"
    return out


def med(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def mannwhitney_exact(a: list[float], b: list[float]) -> float:
    """Exact two-sided Mann-Whitney U p-value by full enumeration.

    Written out rather than imported because this package has no runtime
    dependencies and the samples are tiny (5 vs 5 = 252 partitions), where an
    exact test is both cheap and more honest than a normal approximation.
    Ties contribute 0.5, the standard correction.
    """
    n1, n2 = len(a), len(b)
    if not n1 or not n2:
        return 1.0

    def u_stat(x: list[float], y: list[float]) -> float:
        return (sum(1 for i in x for j in y if i < j)
                + 0.5 * sum(1 for i in x for j in y if i == j))

    observed = u_stat(a, b)
    extreme = min(observed, n1 * n2 - observed)
    pool = a + b
    hits = total = 0
    for combo in itertools.combinations(range(len(pool)), n1):
        picked = set(combo)
        x = [pool[i] for i in combo]
        y = [pool[i] for i in range(len(pool)) if i not in picked]
        u = u_stat(x, y)
        total += 1
        if min(u, n1 * n2 - u) <= extreme:
            hits += 1
    return hits / total if total else 1.0


def span(records: list[dict], key: str) -> str:
    values = [r[key] for r in records]
    if not values:
        return "—"
    low, high = min(values), max(values)
    return f"{low:,}" if low == high else f"{low:,}–{high:,}"


def aggregate(records: list[dict]) -> dict:
    for r in records:
        # What the session actually had to take in, as opposed to what it was
        # billed for: cache reads are the same context re-presented each turn.
        r["new_input"] = r.get("fresh_input", 0) + r.get("cache_creation", 0)
    return {
        "trials": len(records),
        "correct": sum(1 for r in records if r["correct"]),
        "new_input": med([r["new_input"] for r in records]),
        "input_tokens": med([r["input_tokens"] for r in records]),
        "output_tokens": med([r["output_tokens"] for r in records]),
        "turns": med([r["num_turns"] for r in records]),
        "seconds": med([r["duration_ms"] for r in records]) / 1000,
        "cost": med([r["cost_usd"] for r in records]),
        "tool_calls": med([r["tool_calls"] for r in records]),
        "files_read": med([r["files_read"] for r in records]),
        "decoy_hits": med([r["decoy_hits"] for r in records]),
        "off_target_edits": med([r["off_target_edits"] for r in records]),
        "failed_commands": med([r["failed_commands"] for r in records]),
        "correction_cycles": med([r["correction_cycles"] for r in records]),
        "any_decoy": sum(1 for r in records if r["decoy_hits"] > 0),
        "any_correction": sum(1 for r in records if r["correction_cycles"] > 0),
        "slate_tool_calls": sum(r.get("slate_tool_calls", 0) for r in records),
        "total_tool_calls": sum(r["tool_calls"] for r in records),
        # Hook-injected freshness. Unlike slate_tool_calls this does not depend
        # on the agent choosing anything, so it separates "the signal was
        # delivered" from "the agent went looking for it".
        "hook_injections": sum(r.get("hook_injections", 0) for r in records),
        "any_hook": sum(1 for r in records if r.get("hook_injections", 0) > 0),
    }


def markdown(by_arm: dict[str, list[dict]]) -> str:
    arms = [a for a in spec.ARMS if a.name in by_arm]
    agg = {a.name: aggregate(by_arm[a.name]) for a in arms}
    out: list[str] = []

    def w(line: str = "") -> None:
        out.append(line)

    w("# Slate agent benchmark — Flask")
    w()
    w(f"Real headless `claude -p` sessions (`{spec.MODEL}`) against "
      f"[pallets/flask]({spec.REPO_URL.removesuffix('.git')}), implementing a "
      "real merged PR and graded by that PR's own tests.")
    w()
    w("Every number below is **observed**, not modelled: tokens and timings "
      "come from the CLI's result envelope, wrong turns from the tool calls in "
      "the transcript, correctness from pytest. Raw transcripts for every "
      "trial are in `runs/`.")
    w()

    if SKIPPED:
        stale_arms = sorted({r["arm"] for r in SKIPPED})
        revs = sorted({r.get("task_revision", 1) for r in SKIPPED})
        w(f"> **{len(SKIPPED)} records excluded.** `runs/` also holds results "
          f"from task revision {', '.join(str(r) for r in revs)}; this report "
          f"covers revision {spec.TASK_REVISION} only. Affected arms: "
          f"{', '.join(f'`{a}`' for a in stale_arms)}. They are a different "
          "experiment and averaging them in would be meaningless — re-run "
          "those arms to include them.")
        w()

    prov = provenance(by_arm)
    days = sorted({prov[a.name] for a in arms})
    if len(days) > 1:
        w("> **Arms here were not all run on the same day.** Re-running an arm "
          "overwrites its records in place, so this table mixes sweeps:")
        w(">")
        for arm in arms:
            w(f"> - `{arm.name}` — {prov[arm.name]}")
        w(">")
        w("> Comparisons *within* a single day are sound; comparisons across "
          "days carry an extra confound (model updates, account state, time of "
          "day). Where a claim depends on a cross-day comparison it is flagged "
          "at the point it is made.")
        w()
    w("## Setup")
    w()
    w(f"- **Task** — a real merged Flask PR (`{spec.SOLUTION_COMMIT}`, #5928): "
      "make every teardown callback run even when an earlier one raises, and "
      "still surface the errors afterwards. Implemented against the PR's "
      "parent commit. The fix spans `helpers.py`, `ctx.py` and `app.py`, and "
      "nothing in the tree names the feature beforehand — so the answer "
      "cannot be reached by grepping the feature name.")
    w(f"- **Grader** — the PR's own {len(spec.GRADER_TESTS)} test files, "
      "restored *after* the agent stops so they cannot be read or edited "
      "during the run, and each run in its own pytest session. A trial is "
      "correct only if all of them pass **and** it introduces no new failure "
      "in Flask's full suite.")
    w("- **Prompt** — byte-identical in every arm, and describes only the "
      "behaviour, never the file layout or the shape of the fix. Naming those "
      "would hand over the very thing the context is meant to supply.")
    w("- **Delivery** — Claude Code reads `CLAUDE.md`, not `AGENTS.md`, so "
      "each context arm gets a `CLAUDE.md` that `@`-imports the layer (the "
      "remedy the official docs prescribe) and the Slate arms additionally "
      "pass `--mcp-config`. Before the sweep runs, a canary token planted in "
      "the layer must come back from the model, or the run aborts. An earlier "
      "version of this benchmark measured five arms whose context silently "
      "never arrived; the gate exists so that cannot recur.")
    w(f"- **Trials** — {min(a['trials'] for a in agg.values())} per arm; "
      "median reported, full range in brackets.")
    w()
    w("## The arms")
    w()
    for arm in arms:
        w(f"- **`{arm.name}`** ({arm.experiment}) — {arm.blurb}")
    w()
    w("E1 asks what context is worth when it is accurate. E2 keeps everything "
      "identical and makes the context 50 commits and five months out of "
      "date, in the specific way Flask's own history made it: `c2705ffd` "
      "merged the request context into the application context, rewriting "
      "`ctx.py` and deleting `RequestContext` and `_cv_request`. A doc "
      "written before it describes two context objects with two teardown "
      "paths; the task commit has one. The removed names still appear "
      "vestigially in the tree, so searching for them returns just enough to "
      "look plausible.")
    w()

    w("## Headline")
    w()
    total = sum(a["trials"] for a in agg.values())
    solved = sum(a["correct"] for a in agg.values())
    w(f"**{solved} of {total} trials produced a correct solution.** No arm "
      "solved this task, so nothing here supports a claim that a context "
      "layer — Slate's or anyone's — makes an agent more likely to get a hard "
      "change right.")
    w()
    w("What the run does establish is narrower:")
    w()
    w("1. Context measurably speeds up orientation. Documented arms reach a "
      "file the fix touches on tool call 1 rather than 2, and run fewer turns "
      "than `bare`.")
    w("2. Slate's generated layer did that on fewer ingested tokens than a "
      "hand-written doc, and never reproduced a stale claim, because it does "
      "not make prose claims that can rot.")
    slate_mcp = sum(agg[a.name]["slate_tool_calls"]
                    for a in arms if a.context == "slate")
    slate_ops = sum(agg[a.name]["total_tool_calls"]
                    for a in arms if a.context == "slate")
    w(f"3. **Offering the freshness signal still does not work.** Across every "
      f"Slate arm the agent made {slate_mcp} calls to a `slate_*` MCP tool out "
      f"of {slate_ops} tool calls. Injecting it does work — the hooked arms "
      f"received it in every trial without the agent asking.")
    if any(getattr(a, "hooks", False) for a in arms):
        w("4. **The pre-registered hypothesis failed.** Hook delivery did not "
          "reduce decoy hits, the metric chosen in advance to detect an agent "
          "being misled by a stale doc. An unplanned effect did show up in "
          "cost on the stale arm; it is reported below as exploratory, "
          "because that is what it is.")
    w()
    w("## Results")
    w()
    w("| Arm | Correct | Context ingested | Turns | Tool calls | Wall clock "
      "| Billed input | Cost |")
    w("|---|---|---|---|---|---|---|---|")
    for arm in arms:
        a, rs = agg[arm.name], by_arm[arm.name]
        w(f"| `{arm.name}` | {a['correct']}/{a['trials']} "
          f"| {a['new_input']:,.0f} [{span(rs, 'new_input')}] "
          f"| {a['turns']:.0f} [{span(rs, 'num_turns')}] "
          f"| {a['tool_calls']:.0f} [{span(rs, 'tool_calls')}] "
          f"| {a['seconds']:.0f}s "
          f"| {a['input_tokens']:,.0f} "
          f"| ${a['cost']:.3f} |")
    w()
    w("**Context ingested** is fresh input plus cache-creation tokens — the "
      "material the session genuinely had to take in. **Billed input** adds "
      "cache reads, which re-present that same context on every turn; it is "
      "what you pay for, but it scales with turn count rather than with how "
      "much the agent had to learn, so it is reported alongside rather than "
      "as the headline.")
    w()

    w("### Wrong turns")
    w()
    w("| Arm | Decoy hits | Trials hitting a decoy | Off-target edits "
      "| Failed commands | Correction cycles |")
    w("|---|---|---|---|---|---|")
    for arm in arms:
        a, rs = agg[arm.name], by_arm[arm.name]
        w(f"| `{arm.name}` | {a['decoy_hits']:.0f} [{span(rs, 'decoy_hits')}] "
          f"| {a['any_decoy']}/{a['trials']} "
          f"| {a['off_target_edits']:.0f} "
          f"| {a['failed_commands']:.0f} "
          f"| {a['correction_cycles']:.0f} |")
    w()
    w("**Definitions**, all counted mechanically from the transcript by "
      "`run.py`, never judged by hand:")
    w()
    w(f"- *Decoy hit* — a tool call naming {' or '.join(f'`{s}`' for s in spec.DECOY_SYMBOLS)}, "
      "the context objects the refactor deleted. Reaching for one means the "
      "agent is working from the old model of the code.")
    w("- *Off-target edit* — a write to a file outside the set the real PR "
      "touched (its source files plus the changelog and its doc page).")
    w("- *Failed command* — a shell call that exited non-zero.")
    w("- *Correction cycle* — a verification command that failed, followed by "
      "further editing.")
    w("- *Found target after* — tool calls before the agent first touches a "
      "file the real fix changes. Read with care: `app.py` and `ctx.py` are "
      "central enough that an agent opens one early for reasons that have "
      "nothing to do with the task, so this metric floors out around 2-3 in "
      "every arm and discriminates less than the others.")
    w()

    hooked = [a for a in arms if getattr(a, "hooks", False)]
    unhooked_slate = [a for a in arms if a.context == "slate" and not getattr(a, "hooks", False)]
    if hooked:
        w("### Was the freshness signal actually delivered?")
        w()
        w("The first sweep's load-bearing finding was that the agent never "
          "consulted the freshness signal at all, so every other number in it "
          "described prose sitting in the context window rather than the "
          "mechanism Slate exists to provide. These arms replace the *offer* "
          "(an MCP tool the agent may call) with an *injection* (a "
          "SessionStart/PreToolUse hook the agent cannot decline).")
        w()
        w("| Arm | Hooks | Slate MCP tool calls | Hook injections | Trials reached |")
        w("|---|---|---|---|---|")
        for arm in [*unhooked_slate, *hooked]:
            a = agg[arm.name]
            w(f"| `{arm.name}` | {'yes' if getattr(arm, 'hooks', False) else 'no'} "
              f"| {a['slate_tool_calls']} | {a['hook_injections']} "
              f"| {a['any_hook']}/{a['trials']} |")
        w()
        starved = [a.name for a in hooked if agg[a.name]["hook_injections"] == 0]
        if starved:
            w(f"**{', '.join(starved)} recorded zero hook injections.** The "
              "delivery mechanism did not fire, so those arms say nothing about "
              "hooks and must not be read as evidence either way.")
            w()
        w("**This column counts SessionStart only, and undercounts delivery.** "
          "Claude Code writes SessionStart's injected context into the "
          "stream-json transcript but not PreToolUse's, so a PreToolUse warning "
          "that fired and reached the model leaves no trace to count. That was "
          "verified rather than assumed: instrumenting the hook command to log "
          "its own invocations showed both `SessionStart` and `PreToolUse Read` "
          "firing and returning context in a session whose transcript recorded "
          "only the former. Treat the number as a floor on delivery — it "
          "establishes that the mechanism reached every trial, and it cannot "
          "attribute the effect below to one hook or the other.")
        w()

    slate_arms = [a for a in arms if a.context == "slate"]
    if slate_arms:
        used = sum(agg[a.name]["slate_tool_calls"] for a in slate_arms)
        opportunities = sum(agg[a.name]["total_tool_calls"] for a in slate_arms)
        w("### Did the agent use Slate?")
        w()
        w(f"Across the Slate arms the agent made **{used} calls to Slate's own "
          f"MCP tools out of {opportunities} tool calls**.")
        w()
        if used == 0 and not hooked:
            w("Zero. Not a delivery failure — the MCP server reported "
              "`connected`, `slate_read` / `slate_status` / `slate_diff` / "
              "`slate_verify` were all exposed in the session, and the "
              "delivered `AGENTS.md` instructs the agent to run `slate status` "
              "first. Handed a concrete coding task, the agent went straight "
              "to grep and never consulted the layer.")
            w()
            w("This is the most consequential result here, and it is not "
              "about freshness being computed wrongly. A freshness signal is "
              "worth nothing if nothing reads it mid-task. Whatever these "
              "arms show about tokens or turns comes from the prose sitting "
              "in the context window, not from the mechanism Slate exists to "
              "provide.")
        w()

    # The pre-registered hypothesis: injecting freshness changes behaviour that
    # offering it did not. Paired so each hooked arm is read against the arm it
    # is identical to except for delivery.
    pairs = [(u, h) for u in unhooked_slate for h in hooked
             if h.name == f"{u.name}-hooked"]
    if pairs:
        w("### Hook delivery vs. tool offer, head to head")
        w()
        w("Each pair is the same context layer, the same task and the same "
          "grader. The only difference is whether freshness was injected or "
          "offered.")
        w()
        w("| Comparison | Correct | Decoy hits (median) | Trials hitting a decoy "
          "| Turns | Cost |")
        w("|---|---|---|---|---|---|")
        for base, hook in pairs:
            for arm in (base, hook):
                a = agg[arm.name]
                w(f"| `{arm.name}` | {a['correct']}/{a['trials']} "
                  f"| {a['decoy_hits']:.0f} [{span(by_arm[arm.name], 'decoy_hits')}] "
                  f"| {a['any_decoy']}/{a['trials']} "
                  f"| {a['turns']:.0f} | ${a['cost']:.3f} |")
        w()
        w("**How to read this.** `decoy_hits` — reaching for `RequestContext` "
          "or `_cv_request`, the two names the refactor deleted — is what being "
          "misled by a stale doc looks like in a transcript, and it is the "
          "metric hook delivery should move. `correct` was 0/25 across every "
          "arm of the first sweep; it is a floor effect on this task and is "
          "reported as a control, not as the hypothesis.")
        w()
        w("Exact two-sided Mann-Whitney U, computed by enumeration (n=5 per "
          "arm, so 0.0079 is the smallest p this design can produce):")
        w()
        w("| Comparison | Metric | Median | Exact p |")
        w("|---|---|---|---|")
        for base, hook in pairs:
            for key, label in (("decoy_hits", "decoy hits (pre-registered)"),
                               ("tool_calls", "tool calls"),
                               ("num_turns", "turns"),
                               ("new_input", "context ingested")):
                a = [r[key] for r in by_arm[base.name]]
                b = [r[key] for r in by_arm[hook.name]]
                p = mannwhitney_exact(a, b)
                shown = f"**{p:.4f}**" if p < 0.05 else f"{p:.4f}"
                w(f"| `{base.name}` → `{hook.name}` | {label} "
                  f"| {statistics.median(a):,.0f} → {statistics.median(b):,.0f} "
                  f"| {shown} |")
        w()
        w("**What this does and does not license.** The pre-registered metric "
          "moved nowhere (p=1.0, and directionally the wrong way: 1/5 trials "
          "hit a decoy un-hooked, 2/5 hooked). The cost metrics separate "
          "cleanly on the *stale* arm and not at all on the *fresh* one — "
          "which is the interaction the mechanism predicts, since a freshness "
          "signal has nothing to say when nothing is stale, and it is harder "
          "to explain by a confound like model drift or time of day, because "
          "such a confound would move both arms.")
        w()
        w("Three caveats, none of them small. **(1)** Tool calls, turns and "
          "context ingested are not three findings; they are one behavioural "
          "change measured three ways. Cache-creation per turn is near "
          "identical between the arms (1,344 vs 1,294), so the token "
          "difference is the turn difference, and the turn difference is the "
          "tool-call difference. **(2)** This was not the hypothesis. Eight "
          "tests were run; a strict Bonferroni correction over all of them "
          "puts the best result at the edge of significance. **(3)** n=5. The "
          "honest status is a promising exploratory result that needs "
          "replication at higher n, pre-registered on cost rather than "
          "decoys — not a demonstrated win.")
        w()

    if "slate-stale" in agg and "handwritten-stale" in agg:
        s, h = agg["slate-stale"], agg["handwritten-stale"]
        w("### E2: what staleness cost, and what it did not")
        w()
        w(f"- **Correctness: {h['correct']}/{h['trials']} vs "
          f"{s['correct']}/{s['trials']}.** Neither stale arm solved the task "
          "— but neither did any *fresh* arm. Correctness is 0/5 in all five "
          "arms, so this benchmark cannot say anything about context and "
          "correctness on this task. It is a floor effect, not a finding.")
        w(f"- **Decoy hits: {h['any_decoy']}/{h['trials']} trials in "
          f"`handwritten-stale` vs {s['any_decoy']}/{s['trials']} in "
          "`slate-stale`.** This looks like the freshness signal working. It "
          "is not. The agent essentially never called a Slate tool, so no "
          "freshness signal was read in these arms. The real cause is that "
          "Slate's layer — "
          "module maps, file counts, dependency edges — never names "
          "`RequestContext` or `_cv_request` anywhere, while the hand-written "
          "doc describes them in prose. Slate avoided the trap by not making "
          "the kind of claim that can rot, not by detecting that it had.")
        sf = agg.get("slate-fresh")
        if sf:
            w(f"- **Turns and cost across the un-hooked arms are inside the "
              f"noise.** `slate-stale` posts {s['turns']:.0f} turns against "
              f"`slate-fresh`'s {sf['turns']:.0f}, on spreads of "
              f"[{span(by_arm['slate-stale'], 'num_turns')}] and "
              f"[{span(by_arm['slate-fresh'], 'num_turns')}]. Read the paired "
              "table above for the comparison that is actually controlled; no "
              "ranking among the un-hooked arms survives its own error bars.")
        w()
        w("The one defensible reading of E2: a context layer made of scanned "
          "facts degrades more gracefully than a context layer made of prose, "
          "because there is less in it that can become false. That is an "
          "argument for how Slate generates docs. It is not evidence for the "
          "freshness engine, which went unused.")
        w()

    w("## Threats to validity")
    w()
    w("Stated up front, because a benchmark run by the tool's author on the "
      "tool's own behalf deserves the scrutiny:")
    w()
    if any(getattr(a, "hooks", False) for a in arms):
        w("- **The cost result was not the hypothesis.** `decoy_hits` was "
          "pre-registered in `spec.py` as the metric hook delivery should "
          "move; it did not move. The tool-call/turn/token effect was found "
          "afterwards, in data collected to test something else. That is a "
          "weaker epistemic position than it looks in a table, and it is why "
          "it is labelled exploratory throughout. The replication to run is "
          "one that pre-registers cost, at higher n.")
        w("- **Which hook produced the effect is unknown.** SessionStart and "
          "PreToolUse were installed together and the transcript can only "
          "observe the first, so the sweep cannot attribute the difference to "
          "either. A follow-up should run them as separate arms.")
        w("- **Hooked and un-hooked arms differ in one more way than intended.** "
          "The hooked arms carry a `.claude/settings.json` the un-hooked arms "
          "lack. It configures nothing but the hooks, but it is a file in the "
          "tree that the agent could in principle read.")
    w("- **One repo, one task.** Flask is mid-sized, pure Python, and unusually "
      "well organised. The orientation cost of context scales with repo size "
      "and messiness, so E1 here is close to a worst case for Slate; a "
      "sprawling repo would flatter it more. Nothing is claimed beyond this "
      "task until the harness is pointed at more.")
    w("- **Task selection is the load-bearing choice.** An earlier version of "
      "this benchmark used a task whose feature name already existed in the "
      "tree; every agent simply grepped it, landed in the right file within "
      "two tool calls, and no context could have mattered. That run is "
      "discarded. This task was chosen specifically because its feature has "
      "no name in the tree beforehand — which is a real property of the task, "
      "but also one selected *because* it gives context a chance to matter. "
      "Read the result as 'what context is worth on a task where location "
      "must be reasoned about', not as an average over all tasks.")
    w("- **The stale window is one refactor wide.** The doc is 50 commits and "
      "five months behind, and the drift that matters is a single real "
      "commit. That makes attribution clean, but it is a favourable case: a "
      "doc wrong in one specific, relevant way is easier to catch than one "
      "that has rotted diffusely.")
    w("- **The hand-written baseline is written by us.** It is a good-faith "
      "document — accurate at its commit, genuinely useful, no sabotage — but "
      "we wrote both the thing being tested and the thing it is tested "
      "against. It is in `spec.py`; judge it directly.")
    w("- **`bare` is not a straw man, but it is not a ceiling either.** A "
      "strong agent with good search recovers well from having no context. "
      "The interesting comparison is not Slate vs nothing, it is Slate vs an "
      "unmaintained doc — which is what most repos actually have.")
    w("- **Cost figures come from the CLI's own accounting** and reflect list "
      "pricing for the pinned model; they move when prices do.")
    w("- **One model, one agent.** Results are for the pinned model under "
      "Claude Code's headless harness, whose own search tools are strong. A "
      "weaker agent, or one without repo-wide grep, would lean on written "
      "context more; a stronger one, less.")
    w()
    w("## Reproduce")
    w()
    w("```bash")
    w("python benchmarks/agentbench/run.py --setup")
    w("python benchmarks/agentbench/run.py --verify-baseline")
    w(f"python benchmarks/agentbench/run.py --trials {spec.TRIALS}")
    w("python benchmarks/agentbench/report.py > benchmarks/agentbench/RESULTS.md")
    w("```")
    w()
    w("The experiment is pre-registered in `spec.py` — repo, commits, task "
      "text, arms, grader and every metric definition are fixed there before "
      "any agent runs, and `run.py` only executes it.")
    return "\n".join(out) + "\n"


def e3_report(by_arm: dict[str, list[dict]]) -> str:
    """The repair sweep, scored against the numbers fixed in `spec.py`.

    Kept apart from `markdown()` rather than folded into it: E1 prices
    orientation and E3 prices convergence, they share a task and nothing else,
    and one table over both would invite averaging them.
    """
    names = [a.name for a in spec.REPAIR_ARMS]
    # Never mix two E3 measurements. Revision 1's records are archived under
    # runs/e3-rev1/, but a stray sidecar left in place would otherwise be
    # averaged in silently — the same failure `task_revision` guards for E1.
    arms = {n: [r for r in by_arm.get(n, [])
                if r.get("e3_revision", 1) == spec.E3_REVISION]
            for n in names}
    if not any(arms.values()):
        return (f"no E3 records at measurement revision {spec.E3_REVISION} — "
                "run the repair arms first\n")

    def conv(records: list[dict]) -> float:
        """Of the repair jobs a session's own edits created, the fraction closed.

        Pooled over trials rather than averaged per trial: a trial whose edits
        created no jobs has an undefined ratio, and dropping it silently would
        weight the arms differently.
        """
        created = sum(r["suspect_claims_unrepaired"] for r in records)
        return sum(r["claims_repaired"] for r in records) / created if created else 0.0

    lines = [
        "## E3 — the repair loop\n",
        f"Pre-registration: `spec.py` at task revision {spec.TASK_REVISION}, "
        "committed before any agent ran.\n",
        "| | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]

    def row(label: str, fn) -> None:
        lines.append(f"| {label} | " + " | ".join(
            fn(arms[n]) if arms[n] else "—" for n in names) + " |")

    row("trials", lambda rs: str(len(rs)))
    # Invocations vs. injections. The hook is installed in both arms and inert
    # in the control, so the control is *expected* to inject nothing — that is
    # what makes it a control, not a delivery failure.
    row("Stop hook invoked", lambda rs: f"{sum(1 for r in rs if r['stop_hook_fired'])}/{len(rs)}")
    row("Stop hook injected", lambda rs: f"{sum(1 for r in rs if r['stop_hook_injected'])}/{len(rs)}")
    row("repair jobs created", lambda rs: str(sum(r["suspect_claims_unrepaired"] for r in rs)))
    row("repair jobs closed", lambda rs: str(sum(r["claims_repaired"] for r in rs)))
    row("convergence", lambda rs: f"{conv(rs):.0%}")
    row("slate_repair_apply accepted", lambda rs: str(sum(r["repair_apply_accepted"] for r in rs)))
    row("slate_repair_apply rejected", lambda rs: str(sum(r["repair_apply_rejected"] for r in rs)))
    row("correct", lambda rs: f"{sum(1 for r in rs if r['correct'])}/{len(rs)}")
    row("median turns", lambda rs: f"{med([r['num_turns'] for r in rs]):.0f}")
    row("median context", lambda rs: f"{med([r['fresh_input'] + r['cache_creation'] for r in rs]):,.0f}")

    on, off = arms.get("repair-on", []), arms.get("repair-off", [])
    delivery, delivered, relevant = spec.delivery_rate(on)
    lines.append(
        f"\nDelivery (the gate): the hook injected in {delivered} of the "
        f"{relevant} repair-on trial(s) that still had a suspect claim when "
        f"`Stop` fired. The other {len(on) - relevant} had already been closed, "
        f"so silence there is correct and is not counted against delivery.")
    passed, failures = spec.repair_verdict(
        conv(on), conv(off),
        sum(r["repair_apply_accepted"] for r in on),
        sum(r["repair_apply_rejected"] for r in on),
        delivery,
    )
    lines.append(f"\n**spec.repair_verdict() -> {'PASS' if passed else 'FAIL'}**\n")
    for failure in failures:
        lines.append(f"- {failure}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--e3", action="store_true", help="the repair sweep only")
    args = ap.parse_args()

    by_arm = load()
    if not by_arm:
        if SKIPPED:
            revs = sorted({r.get("task_revision", 1) for r in SKIPPED})
            print(
                f"{len(SKIPPED)} result(s) in {RUNS}, but all are from task "
                f"revision {', '.join(str(r) for r in revs)} and this is "
                f"revision {spec.TASK_REVISION}.\n"
                "The task changed, so those records answer a different "
                "question and are not averaged in.\n"
                "Re-run the sweep to produce comparable results.",
                file=sys.stderr)
        else:
            print(f"no results in {RUNS} — run run.py first", file=sys.stderr)
        return 1
    if args.e3:
        print(e3_report(by_arm), end="")
    elif args.json:
        print(json.dumps({k: aggregate(v) for k, v in by_arm.items()}, indent=2))
    else:
        print(markdown(by_arm), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
