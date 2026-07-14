"""Stage 1 — step verdicts (§10 pipeline).

One job per step: load the contract for the step's type, judge via Haiku with
the contract system prompt marked for caching, store the verdict, atomically
decrement the run counter. The last verdict enqueues Stage 2.
"""

from __future__ import annotations

import logging

from anthropic import Anthropic
from psycopg_pool import ConnectionPool

from . import queue
from .config import Config
from .contracts import contract_for
from .queue import Job
from .storage import get_step_payload
from .tenancy import org_transaction
from .verdict_prompt import StepPayload, build_verdict_prompt, parse_verdict_response

log = logging.getLogger(__name__)


def process_verdict(job: Job, pool: ConnectionPool, anthropic: Anthropic, s3, cfg: Config) -> None:
    with org_transaction(pool, job.org_id) as conn:
        row = conn.execute(
            "SELECT step_type, name, storage_key FROM agent_steps WHERE id = %s",
            (job.step_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Step {job.step_id} not found for verdict job {job.id}")
        step_type, name, storage_key = row

        payload = get_step_payload(s3, cfg.minio_bucket, storage_key) if storage_key else {}
        contract = contract_for(step_type)
        system, user = build_verdict_prompt(
            contract,
            StepPayload(
                name=name,
                step_type=step_type,
                inputs=str(payload.get("input", "")),
                output=str(payload.get("output", "")),
            ),
        )

        # Contract system prompt is cached across the run (§8 COGS control #1)
        response = anthropic.messages.create(
            model=cfg.verdict_model,
            max_tokens=512,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        verdict = parse_verdict_response(response.content[0].text)
        passed = verdict.score >= contract.fault_threshold

        conn.execute(
            """
            INSERT INTO step_verdicts (step_id, run_id, org_id, passed, score, failure_class,
                                       judge_reasoning, judge_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (job.step_id, job.run_id, job.org_id, passed, verdict.score,
             verdict.failure_class if not passed else None, verdict.reasoning, cfg.verdict_model),
        )

    # Counter + Stage 2 trigger live OUTSIDE the verdict transaction: the verdict
    # must be committed before it can count as landed.
    remaining = queue.decrement_pending_verdicts(pool, job.run_id)
    if remaining == 0:
        with pool.connection() as conn:
            status_row = conn.execute(
                "SELECT set_config('app.current_org_id', %s, true), "
                "(SELECT status FROM agent_runs WHERE id = %s)",
                (str(job.org_id), job.run_id),
            ).fetchone()
        if status_row and status_row[1] == "failed":
            queue.enqueue_localization(pool, job.org_id, job.run_id)
            log.info("run %s: last verdict landed, localization enqueued", job.run_id)
        else:
            log.info("run %s: verdicts complete (sampled success, no localization)", job.run_id)
