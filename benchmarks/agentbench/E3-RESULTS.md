# E3 — the repair loop (Phase 4)

## Revision 2 — 20 trials, 2026-08-02, `claude-sonnet-5`

**`spec.repair_verdict()` → PASS.** All three pre-registered criteria cleared on
fresh sessions, with the delivery gate's denominator corrected and its threshold
untouched.

Pre-registration: [`spec.py`](spec.py) at `E3_REVISION = 2`, committed in
`2119b4e` before any agent ran. Revision 1's records are archived under
[`runs/e3-rev1/`](runs/e3-rev1) — not re-scored, because a definition written
after seeing the data it failed does not get to score that data.

| Metric | Result | Threshold | |
|---|---|---|---|
| delivery, over trials that still had a job at `Stop` | **6/6 = 100%** | ≥90% | pass |
| convergence gap (repair-on − repair-off) | 100% − 36% = **64pp** | ≥30pp | pass |
| verified repairs exceed rejections | **7 vs 0** | > | pass |

| | `repair-off` | `repair-on` |
|---|---|---|
| trials | 10 | 10 |
| repair jobs created | 14 | 13 |
| repair jobs closed | 5 | 13 |
| convergence | **36%** | **100%** |
| trials that converged at all | 3/10 | 10/10 |
| `slate_repair_apply` accepted / rejected | 0 / 0 | 7 / 0 |
| Stop hook injected | 0/10 (inert by design) | 6/10 |
| correct | 1/10 | 0/10 |
| median turns | 39 | 42 |
| median context | 55,387 | 56,102 |

Trials converging: **10/10 vs 3/10, Fisher one-sided p = 0.0016.**

## What the corrected gate changed

Revision 1 asked "did the hook say something?" across every `repair-on` trial,
read 50%, and voided a sweep in which the hook had spoken every time it had
anything to say. Revision 2 asks the question a delivery gate has to ask —
*when there was something to say, did it say it?*

Here 6 of 10 treatment trials still had a suspect claim when `Stop` fired, and
the hook injected in **all 6**. The other 4 had already closed their jobs, so
silence was correct and is excluded rather than counted as failure. The case
the old gate could not see — silence *and* a claim left suspect — did not occur.

## The finding that replicates, and it is not the headline number

**Roughly half of the treatment's convergence does not go through the gate.**

| route | jobs closed |
|---|---|
| `slate_repair_apply` (verified) | 7 |
| closed before `Stop` ever fired, no gate | 6 |

Revision 1 measured 7 of 14. Revision 2 measures 7 of 13. Two independent runs
agree: the repair loop is doing something, and about half of what it does is
prompting the agent to tidy the docs by hand rather than through the verifier.

**The control converges by rewriting prose directly.** All three converging
control trials replaced the seeded claims with new, accurate prose about code
they had not moved — two of them without touching any Slate command at all
(`reanchor_calls = 0`, `direct_doc_edits = 2`). That is legitimate
documentation behaviour and it does converge the layer. It is also completely
unverified, and it does not trip `verify_repair`'s guard, because the claim
count never drops — the flagged claims are *replaced*, not deleted.

So the honest claim from two sweeps is unchanged by the PASS:

> The layer converges either way. What the repair loop buys is that the
> convergence is *verified* — for about half of it.

## What did not replicate, and why the gap should not be quoted precisely

Control convergence was **69% in revision 1 and 36% in revision 2**, on an
identical design. The control is bimodal — a trial either tidies the docs
thoroughly or ignores them entirely — and with 10 trials the pooled rate swings
widely. Both runs clear the 30pp threshold (31pp, then 64pp), so the *direction*
is stable and the pre-registered criterion is met twice. The *magnitude* is not
estimated well by either run and should not be quoted as a headline.

## Cost, and the absence of a correctness effect

| | revision 1 | revision 2 |
|---|---|---|
| turns, off → on | 38 → 46 | 39 → 42 |
| context, off → on | 49,400 → 61,148 | 55,387 → 56,102 |
| correct, off vs on | 2/10 vs 1/10 | 1/10 vs 0/10 |

Revision 1's ~8-turn, ~12K-context tax mostly did not reappear; revision 2's
delta is 3 turns and under 1K context. Treating either as the cost of the
feature would be over-reading one run.

**Correctness: 1/20 control, 1/20 treatment across both sweeps.** Nothing here
supports a claim that repair helps an agent get the task right, and the plan
never claimed it would. The seeded context makes these arms incomparable to E1
on correctness in any case.

## The product finding, unchanged from revision 1

**Re-anchoring is ungated wherever the agent has a shell.** Phase 2's
`repair.verify_repair` governs the MCP path only. Across both sweeps the control
reached a green layer by editing `read-next.md` with the ordinary `Edit` tool —
sometimes followed by `slate mark` in Bash, sometimes not needed at all because
rewriting the prose is enough. `slate mark` re-anchors a human-owned doc with
nothing verifying that the prose is still true.

This is recorded rather than fixed, because patching the product mid-experiment
is how instruments stop measuring what they claim. The open question is whether
`slate mark` should refuse to re-anchor when the claim count dropped since the
last anchor — the same guard `verify_repair` applies, at the other door. It cuts
against the human case, where `mark` is exactly the right command.

## Threats to validity

- **Convergence ≠ truth.** `claims_repaired` counts claims that stopped being
  flagged. Revision 1's treatment trial 1 repaired its claim by accurately
  describing an implementation that was itself wrong. `adjudicate_e3.py` dumps
  every repair beside the diff it describes for a hand pass.
- **Small denominators.** 13 and 14 jobs across 10 trials each; several trials
  created one job and some created none.
- **Seeded context.** E3 arms carry three seeded claims naming the three files
  the task touches, so their cost and correctness are **not** comparable to the
  E1 arms. Both E3 arms see the identical doc.
- **The delivery denominator is inferred**, not observed at `Stop` time: a trial
  ending with a suspect claim had one at `Stop`, and a trial where the hook
  injected plainly had one. Tight, but it is an inference.

---

## Revision 1 — 20 trials, 2026-08-02. VOID.

`spec.repair_verdict()` → FAIL, on the delivery gate: 5/10 injections against a
90% bar. The gate was mine and it was specified badly — it counted correct
silence on an already-clean layer as a delivery failure. Convergence (100% vs
69%, a 31pp gap) and the kill criterion (7 vs 0) both cleared and licensed
nothing.

Its other contributions, all of which shaped revision 2:

- The plan's premise — "the agent's own edits stale the layer naturally" — is
  false for the claims repair exists for. A stock layer has no hand-written
  claim naming code, so a *perfect* solution produced "nothing to repair". The
  corpus had to be seeded.
- The control was not a control until it got full access; as first built it ran
  read-only, so the arms differed by the repair switch *and* everything `full`
  unlocks.
- `reanchor_calls` initially watched only MCP tool names and reported zero for a
  trial that had plainly re-anchored via Bash.

Records: [`runs/e3-rev1/`](runs/e3-rev1).

## Reproduce

```bash
python benchmarks/agentbench/run.py --arm repair-on --arm repair-off --trials 10
python benchmarks/agentbench/report.py --e3
python benchmarks/agentbench/adjudicate_e3.py
```
