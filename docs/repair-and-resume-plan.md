# Execution plan — the repair-and-resume pivot

**Status:** proposed, not started · **Drafted:** 2026-07-30

---

## Why this pivot

Slate currently delivers a *negative* signal: "this doc is stale, don't trust
it." An agent that receives it has no good move — it can over-explore,
under-trust, or abandon the task. All three hurt the developer, and all three
look identical in a transcript, which is why the 2026-07-27 sweep's cost effect
(tool calls 41→31, context 56.5K→41.5K, stale arm only, p=0.0079) is
uninterpretable: "skipped the bad path" and "gave up earlier" both produce
fewer turns, and correctness was floored at 0/5 in every arm, so there was no
quality axis to trade against.

The pivot replaces the warning with a **repair loop**. When the layer is
untrustworthy, the consumer's own agent fixes the docs — Slate supplies the
deterministic machinery (which claims are suspect, which symbols moved, which
diff is responsible) and the agent supplies the prose. The same division of
labour HyperProbe uses: the vendor ships plumbing, the customer's model does
the reasoning.

Three consequences, in order of importance:

1. **It is measurable.** Repair produces an artifact — the doc was re-anchored
   or it wasn't. That needs no proxy metric and no headroom on task
   correctness, which is the wall the last two benchmark cycles hit.
2. **It is a positive action.** "Here is how to make this trustworthy" is a
   move the agent can execute, unlike "this is unreliable."
3. **It reframes the product.** Slate stops being a context-delivery layer and
   becomes a *memory-consolidation* layer: your agent rediscovers the same
   things every session, and Slate makes the rediscovery stick.

### What repair does *not* buy

The doc went stale because the code changed. To repair it the agent must read
that code — at which point it already knows the truth and the doc is redundant
*for the current session*. Repair does not meaningfully improve the task in
flight. Its value is that the current session's understanding stops
evaporating. Do not pitch it as "resume with trustworthy context"; pitch it as
compounding.

### The enabling machinery already exists

Part B's claim-level trust is what makes this feasible. Without it the repair
unit would be "rewrite `architecture.md`" — expensive, unbounded, likely to
make things worse. With it, the unit is a single sentence with a diff attached:

> Claim 3 in `architecture.md` says `context.get_auto_block` returns X. That
> function's lines moved in `abc1234`. Here is the diff. Rewrite that sentence.

That is a one-turn task with a verifiable result.

---

## Sequencing

```
Phase 0 ──┬─► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
          └─► (fail) stop and redesign
```

Two ordering constraints are hard:

- **Phase 0 gates the whole pivot.** No product code until repair is shown to
  converge.
- **The verifier ships before the writer.** Phase 2 before Phase 3, without
  exception.

Phases 1 and 2 are roughly 2–3 days each and land as normal PRs with
`slate sync` in the same commit (CI's `slate status --ci` gate). Phase 3 is the
first behaviour change a user sees. Phase 4 is the first honest claim the
project can make about the pivot.

---

## Phase 0 — Prove repair converges

*Before any product code.*

**The question.** Given a stale claim plus the diff that staled it, does an
agent produce prose that is *better*, not merely different?

> **Retired criterion — do not revive.** This originally read "such that
> Slate's own verifier turns it fresh, ≥60%". That is circular and was
> measured to be so. Authorship narrowing clears a claim whose prose is newer
> than the code it names, and a repair is newer prose by definition — so
> freshness reads a timestamp the repair just updated. Replacing a stale
> sentence with "`engine.run` returns 9999 purple" turns the doc **fresh**.
> The criterion would have scored ~100% for an agent writing garbage.
>
> The same circularity condemns Phase 2's gate as drafted below; see the note
> there. The live criteria are pre-registered in
> `benchmarks/repairbench/spec.py`.

**Method.** Harvest 10–15 real stale claims from this repo's own history —
`git log` over `.slate/` supplies the ground truth for free, since the layer
has been going stale and being synced for five months. For each claim, hand a
fresh agent the claim text, the refs at risk, and the responsible diff. Score
each rewrite three ways:

- **verifies fresh** — the repaired claim passes `_claims_still_check_out`
- **unverifiable** — fluent prose carrying no checkable refs
- **wrong** — verifies, but does not describe the code correctly

**Exit criteria.** Fixed in `benchmarks/repairbench/spec.py` before any agent
runs. Two balanced arms of 18: sentences a maintainer later rewrote because
the code moved, and sentences flagged for the same reason that the maintainer
deliberately left alone.

| | threshold | catches |
|---|---|---|
| every named symbol exists | ≥90% | confident hallucination |
| rewrite still names code | ≥95% | stripping the backticks so it can never be checked again |
| declines on accurate claims | ≥50% | an agent that rewrites whatever it is shown |

Failing any one means Phases 2 and 3 do not get built and `slate repair` stays
a list for a human. Truth is not on that list — no deterministic check reaches
it — so correctness is adjudicated by hand afterwards.

**Cost.** An afternoon, no code. This is the disconfirming experiment the last
two measurement cycles did not have. Do not skip it.

---

## Phase 1 — Make a suspect claim addressable

You cannot patch what you cannot locate. `Claim` carries `line`
(`slate/claims.py:38`) but **`ClaimVerdict` drops it** (`slate/freshness.py:51`),
so today's suspect list cannot generate a patch target.

**Changes.**

- `ClaimVerdict` gains `line: int` and `doc_path: str`; plumb through
  `_human_claim_verdicts` (`slate/freshness.py:345`). Additive to `as_dict()`,
  so `--json` and MCP shapes stay backward-compatible — the same discipline
  used for the Part B rollout.
- New `slate/repair.py`, pure and LLM-free:
  `repair_tasks(reports) -> list[RepairTask]`, where `RepairTask` carries the
  doc path, line, claim text, refs at risk, and the commits that put them at
  risk. `DocReport.suspect_claims` (`slate/freshness.py:88`) already supplies
  the worklist; this scopes it.
- `slate repair [--json]` — **lists only, writes nothing.**

**Tests.**

- every suspect claim yields exactly one task
- a fresh layer yields no tasks
- the Part B total-walk property survives the plumbing change

**Ships as.** "Slate now tells you exactly which sentences to fix."
Independently valuable to a human, with no agent involved.

---

## Phase 2 — The verification gate

*The false-fresh invariant lives or dies here.*

> **This gate as originally drafted does not work.** It required "the target
> claim becomes fresh", which every edit satisfies — see the retired criterion
> in Phase 0. A gate built on freshness would accept nonsense from every
> trial. What survives is the *shape*: the agent proposes, a deterministic
> check decides. What has to change is the check.

`repair.verify_repair(root, doc, before, after) -> Verdict` must rest on
signals the repair cannot move by existing. The candidate, carried over from
the Phase 0 metrics: every symbol the new sentence names resolves to something
real in the tree, the sentence still names code at all, and no other claim
regresses. Re-anchoring remains a function of `freshness.evaluate` — never of
"the agent reported success" — but freshness is no longer what licenses the
repair.

Generation is cheap and untrusted; verification is deterministic and trusted.
The same asymmetry a proof checker uses. A useful second-order effect: the loop
structurally rewards prose that makes checkable claims, because unverifiable
prose never earns the green status.

### The trap that must be closed first

`_emit` only creates a claim if it has refs (`slate/claims.py:93`). So an agent
can "repair" a claim by **deleting its backticked references** — the claim
vanishes from `human_claims` entirely and the doc goes green.

That is a false `fresh` manufactured by the repair loop itself: the project's
worst-bug invariant, introduced by the feature meant to serve it.

**Guard.** The repaired claim must still resolve to a claim at that location
*carrying refs*. A claim that disappears is a **rejection**, not a repair.

**Tests — write these as adversarial cases.**

| Case | Expected |
|---|---|
| Agent deletes the claim's refs | rejected |
| Fluent prose, no checkable refs | rejected; doc stays non-fresh |
| Fixes claim 3, silently breaks claim 5 | rejected |
| Total claim count drops | rejected |
| Honest repair | accepted; the *engine* re-anchors |

**Exit criterion.** A test named in the spirit of
`test_merged_layer_is_not_falsely_fresh` — e.g.
`test_repair_cannot_manufacture_fresh`.

---

## Phase 3 — Delivery: session-end repair

### Why session-end, not session-start

**Repair-before** asks the agent to reconstruct *why* a doc went stale from a
diff it had no part in. That is archaeology: expensive, error-prone, and it
suspends the developer's task for a detour they did not ask for.

**Repair-after** asks the agent to describe a change *it just made*, with full
context still in the window. Near-free, far more accurate, interrupts nothing.
It also sidesteps the consent problem — at session end the developer already
expects a wrap-up, and `AGENTS.md` already instructs agents to update
`read-next.md` and sync at that point.

Session N pays a small tax; session N+1 starts fresh. Over a repo's life the
layer converges. Blocking repair at session start is the emergency path for an
already-rotten layer — **defer it entirely** until the cheap mode is shown to
converge on its own.

### Changes

- **New `SessionEnd`/`Stop` event in `slate/claudehook.py`**, following the
  existing shape exactly: a constant beside `SESSION_START`/`PRE_TOOL_USE`
  (`slate/claudehook.py:61`), a `session_end_text(reports)` renderer, wired
  through `build_output`. Same contract as every other path in that module —
  `additionalContext` only (`slate/claudehook.py:296`), computes no trust math,
  resolves to silence and exit 0 on any failure.
- **Do not add PreToolUse blocking.** It collides with the landmine that no
  hook path may break a session, and it interrupts at the worst moment.
- **MCP action surface** — `slate_repair_tasks` (read) and
  `slate_repair_apply` (write, added to `_WRITE_TOOLS` at `slate/mcp.py:215`).

  This is *not* a repeat of the delivery failure. The 3-calls-in-687 finding
  was about ambient context nobody asks for. Here the hook has just told the
  agent it has a repair job, so the pull works: the agent knows it has the
  question. **Hooks deliver the instruction; MCP executes it.**

- **Gating** — new `slate agent repair on|off`, **default off**, requiring
  `agentcfg.FULL` (`slate/agentcfg.py:25`). An agent silently editing tracked
  files is how a tool gets uninstalled once. Start with propose-diff; consider
  auto-apply only after Phase 4 data.

---

## Phase 4 — Measure the thing that is now measurable

**Pre-register in `benchmarks/agentbench/spec.py` before running.**
Non-negotiable, given the last two cycles.

**Primary metric.** Suspect-claim count at session end versus session start.

**Secondary.** Verified-repair rate, rejection rate, cost delta.

**This unblocks the benchmark.** `STALE_DOC_COMMIT` is currently `None` at
revision 3 (`benchmarks/agentbench/spec.py:90`) with a note that designing an
honest stale arm needs archaeology — which means the only arm that ever
produced a positive result does not exist at the revision where correctness is
measurable. The repair experiment does not need it: **the agent's own edits
during the task stale the layer naturally.** Let it do the Flask task, then
measure whether the layer is repaired at the end. Staleness is generated by the
experiment rather than constructed for it — cheaper, and more realistic.

**Arms.** `repair-off` versus `repair-on`, revision 3, n ≥ 10.

**Kill criterion, stated in advance.** If verified repairs do not exceed
rejections, or the layer does not measurably converge, the pivot failed —
report it the way `decoy_hits` was reported.

---

## Phase 5 — Ledger and pitch

- **`slate/value.py`** — count claims repaired, and sessions that started fresh
  *because* a prior session repaired them. Same best-effort contract: a ledger
  failure can never break a command.

  This matters more than it looks. HyperProbe closes its loop inside one
  session, so the user feels the value immediately. Slate's repaired doc is
  consumed by a future session or a human, so the feedback is delayed and
  invisible. The ledger is what makes a delayed benefit legible.

- **Docs** — reframe from context delivery to memory consolidation. Update
  `.slate/read-next.md`, append the pivot to `.slate/decisions.md`, run
  `slate sync`.

---

## Risk register

| Risk | Mitigation | Phase |
|---|---|---|
| **Ref-deletion manufactures `fresh`** | claim must survive *with refs*; adversarial test | 2 |
| Verifiable but factually wrong prose | Phase 0 measures the rate; if non-zero, repairs stay proposals | 0 / 3 |
| LLM enters the trust loop | agent proposes, engine decides; mirrors `slate/llm.py` | 2 |
| Unrequested writes to tracked files | default off, `FULL` access, propose-diff | 3 |
| Concurrent repair on two branches | `slate/merge.py` already handles it; add a repair-collision test | 3 |
| Session-end tax annoys developers | bounded worklist; cap tasks per session | 3 |

---

## Explicitly out of scope

- **Replicating the cost effect at higher n.** Uninterpretable until quality
  has headroom; Phase 4 supersedes it.
- **Porting hooks to Codex/Cursor.** Premature until the effect replicates.
- **Blocking session-start repair.** Deferred pending Phase 4 convergence data.
- **Vendor-side inference.** Slate stays zero-dependency and stdlib-only; the
  consumer's agent is the reasoning engine, exactly as `slate/llm.py` already
  assumes — propose, never decide.
