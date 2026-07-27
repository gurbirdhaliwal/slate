# Slate agent benchmark — Flask

Real headless `claude -p` sessions (`claude-sonnet-5`) against [pallets/flask](https://github.com/pallets/flask), implementing a real merged PR and graded by that PR's own tests.

Every number below is **observed**, not modelled: tokens and timings come from the CLI's result envelope, wrong turns from the tool calls in the transcript, correctness from pytest. Raw transcripts for every trial are in `runs/`.

> **Arms here were not all run on the same day.** Re-running an arm overwrites its records in place, so this table mixes sweeps:
>
> - `bare` — 2026-07-26
> - `handwritten-fresh` — 2026-07-26
> - `slate-fresh` — 2026-07-27
> - `handwritten-stale` — 2026-07-26
> - `slate-stale` — 2026-07-27
> - `slate-fresh-hooked` — 2026-07-27
> - `slate-stale-hooked` — 2026-07-27
>
> Comparisons *within* a single day are sound; comparisons across days carry an extra confound (model updates, account state, time of day). Where a claim depends on a cross-day comparison it is flagged at the point it is made.

## Setup

- **Task** — a real merged Flask PR (`fbb6f0bc`, #5928): make every teardown callback run even when an earlier one raises, and still surface the errors afterwards. Implemented against the PR's parent commit. The fix spans `helpers.py`, `ctx.py` and `app.py`, and nothing in the tree names the feature beforehand — so the answer cannot be reached by grepping the feature name.
- **Grader** — the PR's own 2 test files, restored *after* the agent stops so they cannot be read or edited during the run, and each run in its own pytest session. A trial is correct only if all of them pass **and** it introduces no new failure in Flask's full suite.
- **Prompt** — byte-identical in every arm, and describes only the behaviour, never the file layout or the shape of the fix. Naming those would hand over the very thing the context is meant to supply.
- **Delivery** — Claude Code reads `CLAUDE.md`, not `AGENTS.md`, so each context arm gets a `CLAUDE.md` that `@`-imports the layer (the remedy the official docs prescribe) and the Slate arms additionally pass `--mcp-config`. Before the sweep runs, a canary token planted in the layer must come back from the model, or the run aborts. An earlier version of this benchmark measured five arms whose context silently never arrived; the gate exists so that cannot recur.
- **Trials** — 5 per arm; median reported, full range in brackets.

## The arms

- **`bare`** (E1) — No context layer. The agent rediscovers the repo every session.
- **`handwritten-fresh`** (E1) — A good-faith hand-written context doc, accurate right now.
- **`slate-fresh`** (E1) — `slate init` at the task commit; every doc reports fresh.
- **`handwritten-stale`** (E2) — The same doc, written before the context refactor and never updated. Nothing in the repo says it is out of date.
- **`slate-stale`** (E2) — A Slate layer generated before the context refactor; the code then advanced. `slate status` reports the docs stale.
- **`slate-fresh-hooked`** (E1) — `slate init` at the task commit plus hook delivery. Control for the cost of injecting a signal when nothing is wrong.
- **`slate-stale-hooked`** (E2) — The stale Slate layer, with freshness injected by hooks rather than offered as a tool. The agent is told the docs are stale whether or not it asks.

E1 asks what context is worth when it is accurate. E2 keeps everything identical and makes the context 50 commits and five months out of date, in the specific way Flask's own history made it: `c2705ffd` merged the request context into the application context, rewriting `ctx.py` and deleting `RequestContext` and `_cv_request`. A doc written before it describes two context objects with two teardown paths; the task commit has one. The removed names still appear vestigially in the tree, so searching for them returns just enough to look plausible.

## Headline

**0 of 35 trials produced a correct solution.** No arm solved this task, so nothing here supports a claim that a context layer — Slate's or anyone's — makes an agent more likely to get a hard change right.

What the run does establish is narrower:

1. Context measurably speeds up orientation. Documented arms reach a file the fix touches on tool call 1 rather than 2, and run fewer turns than `bare`.
2. Slate's generated layer did that on fewer ingested tokens than a hand-written doc, and never reproduced a stale claim, because it does not make prose claims that can rot.
3. **Offering the freshness signal still does not work.** Across every Slate arm the agent made 3 calls to a `slate_*` MCP tool out of 687 tool calls. Injecting it does work — the hooked arms received it in every trial without the agent asking.
4. **The pre-registered hypothesis failed.** Hook delivery did not reduce decoy hits, the metric chosen in advance to detect an agent being misled by a stale doc. An unplanned effect did show up in cost on the stale arm; it is reported below as exploratory, because that is what it is.

## Results

| Arm | Correct | Context ingested | Turns | Tool calls | Wall clock | Billed input | Cost |
|---|---|---|---|---|---|---|---|
| `bare` | 0/5 | 42,984 [39,558–48,046] | 44 [34–50] | 43 [33–49] | 221s | 1,963,814 | $1.079 |
| `handwritten-fresh` | 0/5 | 44,919 [36,429–47,759] | 38 [32–44] | 37 [31–43] | 206s | 1,844,720 | $1.057 |
| `slate-fresh` | 0/5 | 38,451 [31,088–50,637] | 34 [29–38] | 33 [28–37] | 218s | 1,554,617 | $0.896 |
| `handwritten-stale` | 0/5 | 46,558 [41,435–47,991] | 40 [36–45] | 39 [35–44] | 204s | 1,936,121 | $1.078 |
| `slate-stale` | 0/5 | 56,553 [49,118–58,846] | 42 [40–50] | 41 [39–49] | 306s | 2,332,676 | $1.351 |
| `slate-fresh-hooked` | 0/5 | 38,655 [26,362–43,866] | 28 [20–38] | 27 [19–37] | 185s | 1,276,700 | $0.824 |
| `slate-stale-hooked` | 0/5 | 41,476 [37,507–48,302] | 32 [29–40] | 31 [28–39] | 172s | 1,524,385 | $0.857 |

**Context ingested** is fresh input plus cache-creation tokens — the material the session genuinely had to take in. **Billed input** adds cache reads, which re-present that same context on every turn; it is what you pay for, but it scales with turn count rather than with how much the agent had to learn, so it is reported alongside rather than as the headline.

### Wrong turns

| Arm | Decoy hits | Trials hitting a decoy | Off-target edits | Failed commands | Correction cycles |
|---|---|---|---|---|---|
| `bare` | 0 [0–1] | 1/5 | 0 | 1 | 1 |
| `handwritten-fresh` | 0 [0–1] | 1/5 | 0 | 2 | 1 |
| `slate-fresh` | 0 [0] | 0/5 | 0 | 2 | 1 |
| `handwritten-stale` | 0 [0–1] | 2/5 | 0 | 1 | 1 |
| `slate-stale` | 0 [0–1] | 1/5 | 1 | 2 | 1 |
| `slate-fresh-hooked` | 0 [0] | 0/5 | 0 | 2 | 0 |
| `slate-stale-hooked` | 0 [0–1] | 2/5 | 0 | 1 | 1 |

**Definitions**, all counted mechanically from the transcript by `run.py`, never judged by hand:

- *Decoy hit* — a tool call naming `RequestContext` or `_cv_request`, the context objects the refactor deleted. Reaching for one means the agent is working from the old model of the code.
- *Off-target edit* — a write to a file outside the set the real PR touched (its source files plus the changelog and its doc page).
- *Failed command* — a shell call that exited non-zero.
- *Correction cycle* — a verification command that failed, followed by further editing.
- *Found target after* — tool calls before the agent first touches a file the real fix changes. Read with care: `app.py` and `ctx.py` are central enough that an agent opens one early for reasons that have nothing to do with the task, so this metric floors out around 2-3 in every arm and discriminates less than the others.

### Was the freshness signal actually delivered?

The first sweep's load-bearing finding was that the agent never consulted the freshness signal at all, so every other number in it described prose sitting in the context window rather than the mechanism Slate exists to provide. These arms replace the *offer* (an MCP tool the agent may call) with an *injection* (a SessionStart/PreToolUse hook the agent cannot decline).

| Arm | Hooks | Slate MCP tool calls | Hook injections | Trials reached |
|---|---|---|---|---|
| `slate-fresh` | no | 0 | 0 | 0/5 |
| `slate-stale` | no | 3 | 0 | 0/5 |
| `slate-fresh-hooked` | yes | 0 | 10 | 5/5 |
| `slate-stale-hooked` | yes | 0 | 10 | 5/5 |

**This column counts SessionStart only, and undercounts delivery.** Claude Code writes SessionStart's injected context into the stream-json transcript but not PreToolUse's, so a PreToolUse warning that fired and reached the model leaves no trace to count. That was verified rather than assumed: instrumenting the hook command to log its own invocations showed both `SessionStart` and `PreToolUse Read` firing and returning context in a session whose transcript recorded only the former. Treat the number as a floor on delivery — it establishes that the mechanism reached every trial, and it cannot attribute the effect below to one hook or the other.

### Did the agent use Slate?

Across the Slate arms the agent made **3 calls to Slate's own MCP tools out of 687 tool calls**.


### Hook delivery vs. tool offer, head to head

Each pair is the same context layer, the same task and the same grader. The only difference is whether freshness was injected or offered.

| Comparison | Correct | Decoy hits (median) | Trials hitting a decoy | Turns | Cost |
|---|---|---|---|---|---|
| `slate-fresh` | 0/5 | 0 [0] | 0/5 | 34 | $0.896 |
| `slate-fresh-hooked` | 0/5 | 0 [0] | 0/5 | 28 | $0.824 |
| `slate-stale` | 0/5 | 0 [0–1] | 1/5 | 42 | $1.351 |
| `slate-stale-hooked` | 0/5 | 0 [0–1] | 2/5 | 32 | $0.857 |

**How to read this.** `decoy_hits` — reaching for `RequestContext` or `_cv_request`, the two names the refactor deleted — is what being misled by a stale doc looks like in a transcript, and it is the metric hook delivery should move. `correct` was 0/25 across every arm of the first sweep; it is a floor effect on this task and is reported as a control, not as the hypothesis.

Exact two-sided Mann-Whitney U, computed by enumeration (n=5 per arm, so 0.0079 is the smallest p this design can produce):

| Comparison | Metric | Median | Exact p |
|---|---|---|---|
| `slate-fresh` → `slate-fresh-hooked` | decoy hits (pre-registered) | 0 → 0 | 1.0000 |
| `slate-fresh` → `slate-fresh-hooked` | tool calls | 33 → 27 | 0.4444 |
| `slate-fresh` → `slate-fresh-hooked` | turns | 34 → 28 | 0.4444 |
| `slate-fresh` → `slate-fresh-hooked` | context ingested | 38,451 → 38,655 | 0.6905 |
| `slate-stale` → `slate-stale-hooked` | decoy hits (pre-registered) | 0 → 0 | 1.0000 |
| `slate-stale` → `slate-stale-hooked` | tool calls | 41 → 31 | **0.0159** |
| `slate-stale` → `slate-stale-hooked` | turns | 42 → 32 | **0.0159** |
| `slate-stale` → `slate-stale-hooked` | context ingested | 56,553 → 41,476 | **0.0079** |

**What this does and does not license.** The pre-registered metric moved nowhere (p=1.0, and directionally the wrong way: 1/5 trials hit a decoy un-hooked, 2/5 hooked). The cost metrics separate cleanly on the *stale* arm and not at all on the *fresh* one — which is the interaction the mechanism predicts, since a freshness signal has nothing to say when nothing is stale, and it is harder to explain by a confound like model drift or time of day, because such a confound would move both arms.

Three caveats, none of them small. **(1)** Tool calls, turns and context ingested are not three findings; they are one behavioural change measured three ways. Cache-creation per turn is near identical between the arms (1,344 vs 1,294), so the token difference is the turn difference, and the turn difference is the tool-call difference. **(2)** This was not the hypothesis. Eight tests were run; a strict Bonferroni correction over all of them puts the best result at the edge of significance. **(3)** n=5. The honest status is a promising exploratory result that needs replication at higher n, pre-registered on cost rather than decoys — not a demonstrated win.

### E2: what staleness cost, and what it did not

- **Correctness: 0/5 vs 0/5.** Neither stale arm solved the task — but neither did any *fresh* arm. Correctness is 0/5 in all five arms, so this benchmark cannot say anything about context and correctness on this task. It is a floor effect, not a finding.
- **Decoy hits: 2/5 trials in `handwritten-stale` vs 1/5 in `slate-stale`.** This looks like the freshness signal working. It is not. The agent essentially never called a Slate tool, so no freshness signal was read in these arms. The real cause is that Slate's layer — module maps, file counts, dependency edges — never names `RequestContext` or `_cv_request` anywhere, while the hand-written doc describes them in prose. Slate avoided the trap by not making the kind of claim that can rot, not by detecting that it had.
- **Turns and cost across the un-hooked arms are inside the noise.** `slate-stale` posts 42 turns against `slate-fresh`'s 34, on spreads of [40–50] and [29–38]. Read the paired table above for the comparison that is actually controlled; no ranking among the un-hooked arms survives its own error bars.

The one defensible reading of E2: a context layer made of scanned facts degrades more gracefully than a context layer made of prose, because there is less in it that can become false. That is an argument for how Slate generates docs. It is not evidence for the freshness engine, which went unused.

## Threats to validity

Stated up front, because a benchmark run by the tool's author on the tool's own behalf deserves the scrutiny:

- **The cost result was not the hypothesis.** `decoy_hits` was pre-registered in `spec.py` as the metric hook delivery should move; it did not move. The tool-call/turn/token effect was found afterwards, in data collected to test something else. That is a weaker epistemic position than it looks in a table, and it is why it is labelled exploratory throughout. The replication to run is one that pre-registers cost, at higher n.
- **Which hook produced the effect is unknown.** SessionStart and PreToolUse were installed together and the transcript can only observe the first, so the sweep cannot attribute the difference to either. A follow-up should run them as separate arms.
- **Hooked and un-hooked arms differ in one more way than intended.** The hooked arms carry a `.claude/settings.json` the un-hooked arms lack. It configures nothing but the hooks, but it is a file in the tree that the agent could in principle read.
- **One repo, one task.** Flask is mid-sized, pure Python, and unusually well organised. The orientation cost of context scales with repo size and messiness, so E1 here is close to a worst case for Slate; a sprawling repo would flatter it more. Nothing is claimed beyond this task until the harness is pointed at more.
- **Task selection is the load-bearing choice.** An earlier version of this benchmark used a task whose feature name already existed in the tree; every agent simply grepped it, landed in the right file within two tool calls, and no context could have mattered. That run is discarded. This task was chosen specifically because its feature has no name in the tree beforehand — which is a real property of the task, but also one selected *because* it gives context a chance to matter. Read the result as 'what context is worth on a task where location must be reasoned about', not as an average over all tasks.
- **The stale window is one refactor wide.** The doc is 50 commits and five months behind, and the drift that matters is a single real commit. That makes attribution clean, but it is a favourable case: a doc wrong in one specific, relevant way is easier to catch than one that has rotted diffusely.
- **The hand-written baseline is written by us.** It is a good-faith document — accurate at its commit, genuinely useful, no sabotage — but we wrote both the thing being tested and the thing it is tested against. It is in `spec.py`; judge it directly.
- **`bare` is not a straw man, but it is not a ceiling either.** A strong agent with good search recovers well from having no context. The interesting comparison is not Slate vs nothing, it is Slate vs an unmaintained doc — which is what most repos actually have.
- **Cost figures come from the CLI's own accounting** and reflect list pricing for the pinned model; they move when prices do.
- **One model, one agent.** Results are for the pinned model under Claude Code's headless harness, whose own search tools are strong. A weaker agent, or one without repo-wide grep, would lean on written context more; a stronger one, less.

## Reproduce

```bash
python benchmarks/agentbench/run.py --setup
python benchmarks/agentbench/run.py --verify-baseline
python benchmarks/agentbench/run.py --trials 5
python benchmarks/agentbench/report.py > benchmarks/agentbench/RESULTS.md
```

The experiment is pre-registered in `spec.py` — repo, commits, task text, arms, grader and every metric definition are fixed there before any agent runs, and `run.py` only executes it.
