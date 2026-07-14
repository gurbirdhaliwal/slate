"""Stage 2 — fault localization (§10). THIS IS THE CORE IP — HAND-CODE.

Deterministic walk over the step graph in topological order:
  origin-faulted := verdict failed AND all parent steps passed
  propagated     := verdict failed AND >=1 ancestor origin/propagated
Exactly one origin -> diagnosis (method 'deterministic'). Ambiguous (0 or 2+
origins, or run failed but all steps passed) -> one Sonnet call over the full
graph (method 'escalated'). The escalation prompt demands quoted evidence and
forbids naming a step without it — an unsupported diagnosis is worse than none.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from anthropic import Anthropic
from psycopg_pool import ConnectionPool

from .config import Config
from .queue import Job
from .taxonomy import FAILURE_CLASSES
from .tenancy import org_transaction

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepNode:
    id: UUID
    seq: int
    parent_ids: tuple[UUID, ...]
    step_type: str
    name: str
    cost_usd: Decimal | None
    passed: bool | None  # None if this step has no verdict yet
    failure_class: str | None
    reasoning: str | None


@dataclass(frozen=True)
class Diagnosis:
    origin_step_id: UUID | None
    propagated_step_ids: tuple[UUID, ...]
    failure_class: str
    evidence: str | None
    explanation: str | None
    method: str  # 'deterministic' | 'escalated'
    escalation_model: str | None


def process_localization(job: Job, pool: ConnectionPool, anthropic: Anthropic, cfg: Config) -> None:
    with org_transaction(pool, job.org_id) as conn:
        steps = _load_graph(conn, job.run_id)
        diagnosis = localize(steps)
        if diagnosis is None:
            diagnosis = _escalate(steps, anthropic, cfg)
        wasted = _wasted_cost(steps, diagnosis.origin_step_id)
        conn.execute(
            """
            INSERT INTO diagnoses (run_id, org_id, origin_step_id, propagated_step_ids,
                                   failure_class, evidence, explanation, method,
                                   escalation_model, wasted_cost_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (job.run_id, job.org_id, diagnosis.origin_step_id,
             list(diagnosis.propagated_step_ids), diagnosis.failure_class,
             diagnosis.evidence, diagnosis.explanation, diagnosis.method,
             diagnosis.escalation_model, wasted),
        )
    # TODO(Phase 1): emit Slack/webhook alert with origin step, class, wasted cost (§5 step 7)
    log.info("run %s diagnosed: %s at %s (%s)",
             job.run_id, diagnosis.failure_class, diagnosis.origin_step_id, diagnosis.method)


def localize(steps: list[StepNode]) -> Diagnosis | None:
    """Deterministic walk. Returns None when the graph is ambiguous and must escalate."""
    by_id = {s.id: s for s in steps}
    faulted = {s.id for s in steps if s.passed is False}
    if not faulted:
        return None  # run failed but every step passed — escalate

    origins: list[StepNode] = []
    propagated: list[UUID] = []
    for step in sorted(steps, key=lambda s: s.seq):
        if step.id not in faulted:
            continue
        has_faulted_ancestor = _has_faulted_ancestor(step, by_id, faulted)
        if has_faulted_ancestor:
            propagated.append(step.id)
        else:
            origins.append(step)

    if len(origins) != 1:
        return None  # 0 or 2+ candidate origins — escalate

    origin = origins[0]
    return Diagnosis(
        origin_step_id=origin.id,
        propagated_step_ids=tuple(propagated),
        failure_class=origin.failure_class or "planning_error",
        evidence=origin.reasoning,
        explanation=None,
        method="deterministic",
        escalation_model=None,
    )


def _has_faulted_ancestor(step: StepNode, by_id: dict[UUID, StepNode], faulted: set[UUID]) -> bool:
    seen: set[UUID] = set()
    stack = list(step.parent_ids)
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in by_id:
            continue
        seen.add(pid)
        if pid in faulted:
            return True
        stack.extend(by_id[pid].parent_ids)
    return False


def _escalate(steps: list[StepNode], anthropic: Anthropic, cfg: Config) -> Diagnosis:
    """One Sonnet call over the full graph + all verdicts. Evidence is mandatory."""
    graph = [
        {
            "step_id": str(s.id), "seq": s.seq, "type": s.step_type, "name": s.name,
            "parents": [str(p) for p in s.parent_ids],
            "verdict": {"passed": s.passed, "failure_class": s.failure_class,
                        "reasoning": s.reasoning},
        }
        for s in sorted(steps, key=lambda s: s.seq)
    ]
    system = f"""You are a causal debugger for multi-step AI agent runs. You receive the
full step graph of a FAILED run with per-step verdicts. Identify the ORIGIN step:
the earliest step that produced a faulty output from sound inputs. Steps that
failed because they were fed garbage are propagated damage, not the origin.

You MUST quote evidence from the verdicts you are given. Never name a step
without quoted evidence supporting it — an unsupported diagnosis is worse than none.
If the evidence is insufficient to name any step, set origin_step_id to null.

Respond with ONLY a JSON object:
{{"origin_step_id": "<uuid or null>", "failure_class": "<one of: {", ".join(FAILURE_CLASSES)}>",
"propagated_step_ids": ["<uuid>", ...], "evidence": "<quoted spans>",
"explanation": "<one-paragraph causal narrative>"}}"""

    response = anthropic.messages.create(
        model=cfg.escalation_model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": json.dumps({"steps": graph})}],
    )
    raw = response.content[0].text.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(raw)
    failure_class = parsed.get("failure_class")
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"Escalation returned unknown failure class: {failure_class}")
    origin = parsed.get("origin_step_id")
    return Diagnosis(
        origin_step_id=UUID(origin) if origin else None,
        propagated_step_ids=tuple(UUID(p) for p in parsed.get("propagated_step_ids", [])),
        failure_class=failure_class,
        evidence=str(parsed.get("evidence", "")),
        explanation=str(parsed.get("explanation", "")),
        method="escalated",
        escalation_model=cfg.escalation_model,
    )


def _wasted_cost(steps: list[StepNode], origin_id: UUID | None) -> Decimal | None:
    """Cost of the origin step + everything downstream of it (§9 diagnoses)."""
    if origin_id is None:
        return None
    children: dict[UUID, list[UUID]] = {}
    for s in steps:
        for p in s.parent_ids:
            children.setdefault(p, []).append(s.id)
    downstream: set[UUID] = set()
    stack = [origin_id]
    while stack:
        node = stack.pop()
        if node in downstream:
            continue
        downstream.add(node)
        stack.extend(children.get(node, []))
    total = sum((s.cost_usd for s in steps if s.id in downstream and s.cost_usd), Decimal(0))
    return total


def _load_graph(conn, run_id: UUID) -> list[StepNode]:
    rows = conn.execute(
        """
        SELECT s.id, s.seq, s.parent_step_ids, s.step_type, s.name, s.cost_usd,
               v.passed, v.failure_class, v.judge_reasoning
        FROM agent_steps s
        LEFT JOIN step_verdicts v ON v.step_id = s.id
        WHERE s.run_id = %s
        ORDER BY s.seq
        """,
        (run_id,),
    ).fetchall()
    return [
        StepNode(
            id=r[0], seq=r[1], parent_ids=tuple(r[2] or ()), step_type=r[3], name=r[4],
            cost_usd=r[5], passed=r[6], failure_class=r[7], reasoning=r[8],
        )
        for r in rows
    ]
