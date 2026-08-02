# E3 — the repair loop (Phase 4)

**20 trials, 2026-08-02, `claude-sonnet-5`. `spec.repair_verdict()` → FAIL, and
the failure is VOID rather than negative: the delivery gate I wrote cannot tell
"the hook was broken" from "the hook had nothing to say". Under the terms fixed
in advance this sweep does not license a conclusion.**

Pre-registration: [`spec.py`](spec.py), committed in `633adaa` before any agent
ran. Raw records and transcripts in [`runs/`](runs).

## The pre-registered scorecard

| Metric | Result | Threshold | |
|---|---|---|---|
| Stop hook injected (delivery **gate**) | 5/10 = 50% | ≥90% | **void** |
| convergence gap (repair-on − repair-off) | 100% − 69% = **31pp** | ≥30pp | pass |
| verified repairs exceed rejections | 7 vs 0 | > | pass |

Two of three cleared. The gate did not, and a gate is not a metric you get to
average away — it decides whether the other two mean anything.

## Why the gate is void, and why that is my error not the product's

`MIN_DELIVERY` asked: in what fraction of `repair-on` trials did the Stop hook
inject something? Answer: 5 of 10. But the hook is *supposed* to stay silent
when the layer is clean, and in all five silent trials the layer **was** clean —
`suspect_claims_end == 0`, with the claims already closed before the session
ended. The hook fired once in each (no continuation, because it had nothing to
continue for) and correctly said nothing.

So the gate conflated two opposite things:

| | trials | hook behaviour |
|---|---|---|
| still had a job at Stop time | 5 | injected — 5/5 |
| already clean at Stop time | 5 | silent — correct |

**Corrected delivery is 5/5 = 100%.** That reading is *post-hoc* and does not
retroactively license a PASS. It is stated here because the alternative — filing
"delivery 50%" without explanation — would be the more misleading of the two.

The fix for a revision 2 of this gate: measure delivery against the trials that
still had a suspect claim when `Stop` fired, not against all trials. The
quantity was already recorded, so no new judgement enters — but the verdict
still has to come from a fresh run, because a gate rewritten after seeing the
data it failed is not a gate.

## What the sweep found anyway

### Convergence is bought by attestation, not by repair

The cleanest result in the data, and it is not the one Phase 4 set out to find:

**Calling a re-anchor tool predicts convergence perfectly, in both arms.**

| | trials with a re-anchor call | converged |
|---|---|---|
| `repair-off` | 5/10 | those 5 closed 11 of 11 jobs |
| `repair-off` | the other 5 | closed 0 of 5 |
| `repair-on` | 10/10 | closed 14 of 14 |

Every control closure went through a **direct `Edit` of `read-next.md` plus
`slate mark` typed into Bash**. No `verify_repair`, no check that the claims
survived, nothing. The layer went green because the agent said so.

### The real treatment effect is on *whether the agent tidies at all*

| | re-anchored the layer |
|---|---|
| `repair-on` | **10/10** |
| `repair-off` | **5/10** |

Fisher exact one-sided **p = 0.0163**. Turning the repair switch on doubled the
rate at which the agent did anything about the docs. That is a real behavioural
effect and it echoes the 2026-07-27 finding: *offering* a documentation action
gets 3 calls in 687, *injecting* it reaches every session.

### But only half of the treatment's closures were verified

| route | jobs closed |
|---|---|
| `slate_repair_apply` (gate-checked) | 7 |
| attestation only (same route as the control) | 7 |

The repair loop is doing something. What it is mostly doing is prompting the
agent to attest, not to repair.

### The gate never refused anything

7 applies, **0 rejections**. The kill criterion passes trivially, and therefore
tells us nothing about what happens when an agent proposes a bad repair. Phase
0 measured that question properly; this sweep did not test it at all.

### It is not free, and it does not help correctness

| | repair-off | repair-on |
|---|---|---|
| correct | 2/10 | 1/10 |
| median turns | 38 | 46 |
| median context | 49,400 | 61,148 |

~8 turns and ~12K context per session, for no correctness benefit. Correctness
running *lower* in the treatment arm is within noise at n=10 and should not be
read as harm — but nothing here supports a claim that repair helps an agent get
the task right, and the plan never claimed it would.

## The product finding: `slate mark` is an ungated door

Phase 2 built `repair.verify_repair` so a repair could not manufacture a false
`fresh` — a rewrite that strips its backticks is refused, because the claim
would vanish from the trust surface.

**That gate governs the MCP path only.** Every single control closure here went
around it: edit the file with the ordinary `Edit` tool, then run `slate mark` in
a shell. An agent with shell access — which `bypassPermissions` grants, and
which any real user grants their coding agent — needs neither `slate_repair_apply`
nor full MCP access to re-stamp a doc's anchor.

`slate mark` re-anchors a human-owned doc with **nothing verifying that the
prose is still true**. It is the documented, intended command for a human who
has actually reviewed the doc. It is also, for an agent, a one-line way to turn
the whole layer green. This is recorded rather than fixed here, because fixing
the product mid-experiment is how instruments stop measuring what they claim.

## Threats to validity

- **Void gate.** The headline. Nothing below it is licensed until a re-run.
- **Small denominators.** 14 and 16 jobs across 10 trials each; several trials
  created one job, one created none. The convergence percentages are coarse.
- **Convergence ≠ truth.** `claims_repaired` counts claims that stopped being
  flagged. `repair-on` trial 1 repaired its claim by accurately describing an
  implementation that was itself wrong (`_session` as a property returning
  `self.session`, the inverse of the real PR). The layer tracked the code; the
  code was not right. `adjudicate_e3.py` dumps every repair beside the diff it
  describes for the hand pass.
- **Seeded context.** E3 arms carry three seeded claims naming the three files
  the task touches, so their cost and correctness are **not** comparable to the
  E1 arms. Both E3 arms see the identical doc, so the within-E3 comparison is
  unaffected.
- **The control was wrong for the first five treatment trials** and was rebuilt
  (`79e2a58`); `repair-off` ran entirely against the corrected construction.

## Reproduce

```bash
python benchmarks/agentbench/run.py --arm repair-off --arm repair-on --trials 10
python benchmarks/agentbench/report.py --e3
python benchmarks/agentbench/adjudicate_e3.py
```
