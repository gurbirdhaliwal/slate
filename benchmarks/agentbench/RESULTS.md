# Slate agent benchmark — Flask

Real headless `claude -p` sessions (`claude-sonnet-5`) against [pallets/flask](https://github.com/pallets/flask), implementing a real merged PR and graded by that PR's own tests.

Every number below is **observed**, not modelled: tokens and timings come from the CLI's result envelope, wrong turns from the tool calls in the transcript, correctness from pytest. Raw transcripts for every trial are in `runs/`.

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

E1 asks what context is worth when it is accurate. E2 keeps everything identical and makes the context 50 commits and five months out of date, in the specific way Flask's own history made it: `c2705ffd` merged the request context into the application context, rewriting `ctx.py` and deleting `RequestContext` and `_cv_request`. A doc written before it describes two context objects with two teardown paths; the task commit has one. The removed names still appear vestigially in the tree, so searching for them returns just enough to look plausible.

## Headline

**0 of 25 trials produced a correct solution.** No arm solved this task, so nothing here supports a claim that a context layer — Slate's or anyone's — makes an agent more likely to get a hard change right.

What the run does establish is narrower and mostly uncomfortable:

1. Context measurably speeds up orientation. Documented arms reach a file the fix touches on tool call 1 rather than 2, and run fewer turns than `bare`.
2. Slate's generated layer did that on fewer ingested tokens than a hand-written doc, and never reproduced a stale claim, because it does not make prose claims that can rot.
3. The agent never called a Slate tool once — see below. The freshness engine, which is the product's entire thesis, was not exercised by any of these 25 sessions.

## Results

| Arm | Correct | Context ingested | Turns | Tool calls | Wall clock | Billed input | Cost |
|---|---|---|---|---|---|---|---|
| `bare` | 0/5 | 42,984 [39,558–48,046] | 44 [34–50] | 43 [33–49] | 221s | 1,963,814 | $1.079 |
| `handwritten-fresh` | 0/5 | 44,919 [36,429–47,759] | 38 [32–44] | 37 [31–43] | 206s | 1,844,720 | $1.057 |
| `slate-fresh` | 0/5 | 41,251 [28,594–44,913] | 37 [24–42] | 36 [23–41] | 199s | 1,785,788 | $0.988 |
| `handwritten-stale` | 0/5 | 46,558 [41,435–47,991] | 40 [36–45] | 39 [35–44] | 204s | 1,936,121 | $1.078 |
| `slate-stale` | 0/5 | 38,798 [30,966–42,742] | 29 [23–42] | 28 [22–41] | 185s | 1,398,621 | $0.847 |

**Context ingested** is fresh input plus cache-creation tokens — the material the session genuinely had to take in. **Billed input** adds cache reads, which re-present that same context on every turn; it is what you pay for, but it scales with turn count rather than with how much the agent had to learn, so it is reported alongside rather than as the headline.

### Wrong turns

| Arm | Decoy hits | Trials hitting a decoy | Off-target edits | Failed commands | Correction cycles |
|---|---|---|---|---|---|
| `bare` | 0 [0–1] | 1/5 | 0 | 1 | 1 |
| `handwritten-fresh` | 0 [0–1] | 1/5 | 0 | 2 | 1 |
| `slate-fresh` | 0 [0] | 0/5 | 0 | 2 | 1 |
| `handwritten-stale` | 0 [0–1] | 2/5 | 0 | 1 | 1 |
| `slate-stale` | 0 [0] | 0/5 | 0 | 1 | 0 |

**Definitions**, all counted mechanically from the transcript by `run.py`, never judged by hand:

- *Decoy hit* — a tool call naming `RequestContext` or `_cv_request`, the context objects the refactor deleted. Reaching for one means the agent is working from the old model of the code.
- *Off-target edit* — a write to a file outside the set the real PR touched (its source files plus the changelog and its doc page).
- *Failed command* — a shell call that exited non-zero.
- *Correction cycle* — a verification command that failed, followed by further editing.
- *Found target after* — tool calls before the agent first touches a file the real fix changes. Read with care: `app.py` and `ctx.py` are central enough that an agent opens one early for reasons that have nothing to do with the task, so this metric floors out around 2-3 in every arm and discriminates less than the others.

### Did the agent use Slate?

Across the Slate arms the agent made **0 calls to Slate's own MCP tools out of 320 tool calls**.

Zero. Not a delivery failure — the MCP server reported `connected`, `slate_read` / `slate_status` / `slate_diff` / `slate_verify` were all exposed in the session, and the delivered `AGENTS.md` instructs the agent to run `slate status` first. Handed a concrete coding task, the agent went straight to grep and never consulted the layer.

This is the most consequential result here, and it is not about freshness being computed wrongly. A freshness signal is worth nothing if nothing reads it mid-task. Whatever these arms show about tokens or turns comes from the prose sitting in the context window, not from the mechanism Slate exists to provide.

### E2: what staleness cost, and what it did not

- **Correctness: 0/5 vs 0/5.** Neither stale arm solved the task — but neither did any *fresh* arm. Correctness is 0/5 in all five arms, so this benchmark cannot say anything about context and correctness on this task. It is a floor effect, not a finding.
- **Decoy hits: 2/5 trials in `handwritten-stale` vs 0/5 in `slate-stale`.** This looks like the freshness signal working. It is not. The agent never called a Slate tool, so no freshness signal was ever read. The real cause is that Slate's layer — module maps, file counts, dependency edges — never names `RequestContext` or `_cv_request` anywhere, while the hand-written doc describes them in prose. Slate avoided the trap by not making the kind of claim that can rot, not by detecting that it had.
- **Turns and cost differences between arms are inside the noise.** `slate-stale` posts the lowest medians in the table (29 turns, $0.847), *better* than `slate-fresh` at 37 turns. A stale layer outperforming a fresh one is not a mechanism; it is five samples with a 23-42 turn spread. No ranking in this table survives its own error bars.

The one defensible reading of E2: a context layer made of scanned facts degrades more gracefully than a context layer made of prose, because there is less in it that can become false. That is an argument for how Slate generates docs. It is not evidence for the freshness engine, which went unused.

## Threats to validity

Stated up front, because a benchmark run by the tool's author on the tool's own behalf deserves the scrutiny:

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
