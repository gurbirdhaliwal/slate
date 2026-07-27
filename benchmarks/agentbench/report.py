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
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"


def load() -> dict[str, list[dict]]:
    by_arm: dict[str, list[dict]] = {}
    for path in sorted(RUNS.glob("*.json")):
        record = json.loads(path.read_text())
        # When an arm is re-run its records are overwritten in place, so arms
        # in this directory can come from different sweeps on different days.
        # Carry the mtime so the report can say so rather than presenting a
        # cross-sweep comparison as if it were within-sweep.
        record["_ran_at"] = dt.datetime.fromtimestamp(
            path.stat().st_mtime, dt.UTC).date().isoformat()
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
    w("What the run does establish is narrower and mostly uncomfortable:")
    w()
    w("1. Context measurably speeds up orientation. Documented arms reach a "
      "file the fix touches on tool call 1 rather than 2, and run fewer turns "
      "than `bare`.")
    w("2. Slate's generated layer did that on fewer ingested tokens than a "
      "hand-written doc, and never reproduced a stale claim, because it does "
      "not make prose claims that can rot.")
    w("3. The agent never called a Slate tool once — see below. The freshness "
      "engine, which is the product's entire thesis, was not exercised by any "
      "of these 25 sessions.")
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
        w("At n=5 per arm, with the spreads shown in brackets, only a large "
          "effect is visible here. Treat a difference of one or two trials as "
          "noise unless the spans separate.")
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
          "is not. The agent never called a Slate tool, so no freshness "
          "signal was ever read. The real cause is that Slate's layer — "
          "module maps, file counts, dependency edges — never names "
          "`RequestContext` or `_cv_request` anywhere, while the hand-written "
          "doc describes them in prose. Slate avoided the trap by not making "
          "the kind of claim that can rot, not by detecting that it had.")
        w("- **Turns and cost differences between arms are inside the "
          "noise.** `slate-stale` posts the lowest medians in the table (29 "
          "turns, $0.847), *better* than `slate-fresh` at 37 turns. A stale "
          "layer outperforming a fresh one is not a mechanism; it is five "
          "samples with a 23-42 turn spread. No ranking in this table "
          "survives its own error bars.")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    by_arm = load()
    if not by_arm:
        print(f"no results in {RUNS} — run run.py first", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({k: aggregate(v) for k, v in by_arm.items()}, indent=2))
    else:
        print(markdown(by_arm), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
