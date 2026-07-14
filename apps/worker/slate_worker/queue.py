"""Postgres job queue — HAND-CODED (§10/§13).

Wrong semantics here mean jobs silently lost or run twice. The claim is a
single atomic UPDATE over a SKIP LOCKED subselect, safe at any worker count.
Dead jobs stay in the table for inspection; never auto-delete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

CLAIM_SQL = """
UPDATE analysis_jobs SET status = 'running', attempts = attempts + 1, locked_at = now()
WHERE id = (
  SELECT id FROM analysis_jobs
  WHERE status = 'queued' AND run_after <= now()
  ORDER BY created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING id, org_id, run_id, step_id, kind, attempts, max_attempts;
"""


@dataclass(frozen=True)
class Job:
    id: UUID
    org_id: UUID
    run_id: UUID
    step_id: UUID | None
    kind: str  # 'step_verdict' | 'localization'
    attempts: int
    max_attempts: int


def claim_one(pool: ConnectionPool) -> Job | None:
    """Claim the oldest runnable job, or None if the queue is empty."""
    with pool.connection() as conn:
        row = conn.execute(CLAIM_SQL).fetchone()
    if row is None:
        return None
    return Job(*row)


def mark_done(pool: ConnectionPool, job: Job) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE analysis_jobs SET status = 'done' WHERE id = %s", (job.id,))


def mark_dead(pool: ConnectionPool, job: Job, exc: BaseException) -> None:
    log.error("job %s dead after %d attempts: %s", job.id, job.attempts, exc)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE analysis_jobs SET status = 'dead', last_error = %s WHERE id = %s",
            (repr(exc)[:2000], job.id),
        )


def requeue(pool: ConnectionPool, job: Job, exc: BaseException, run_after: datetime) -> None:
    log.warning("job %s attempt %d failed, retrying at %s: %s", job.id, job.attempts, run_after, exc)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE analysis_jobs SET status = 'queued', run_after = %s, last_error = %s "
            "WHERE id = %s",
            (run_after, repr(exc)[:2000], job.id),
        )


def backoff_deadline(attempts: int) -> datetime:
    """Exponential backoff: 2s, 4s, 8s (§10)."""
    return datetime.now(timezone.utc) + timedelta(seconds=2**attempts)


def enqueue_localization(pool: ConnectionPool, org_id: UUID, run_id: UUID) -> None:
    """Stage 2 trigger — called by the verdict path when the last verdict lands."""
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO analysis_jobs (org_id, run_id, kind) VALUES (%s, %s, 'localization')",
            (org_id, run_id),
        )


def decrement_pending_verdicts(pool: ConnectionPool, run_id: UUID) -> int:
    """Atomic run counter (§10): UPDATE ... RETURNING, never read-then-write.

    Returns the number of verdicts still pending; 0 means this was the last
    one and the caller must enqueue the localization job.
    """
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE run_analysis_progress SET pending_verdicts = pending_verdicts - 1 "
            "WHERE run_id = %s RETURNING pending_verdicts",
            (run_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"No run_analysis_progress row for run {run_id}")
    return int(row[0])
