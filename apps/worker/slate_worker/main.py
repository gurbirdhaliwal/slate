"""Worker entrypoint — the loop structure is HAND-CODED (§10).

WORKER_CONCURRENCY threads per container (verdict work is IO-bound on the
Anthropic API); scale further with compose replicas — SKIP LOCKED makes claims
safe across any number of workers.
"""

from __future__ import annotations

import logging
import threading
import time

from anthropic import Anthropic
from psycopg_pool import ConnectionPool

from . import queue
from .config import Config, load_config
from .localization import process_localization
from .storage import make_s3_client
from .token_bucket import TokenBucket
from .verdicts import process_verdict

log = logging.getLogger(__name__)


def work_loop(pool: ConnectionPool, limiter: TokenBucket, anthropic: Anthropic, s3, cfg: Config) -> None:
    while True:
        job = queue.claim_one(pool)
        if job is None:
            time.sleep(0.5)  # queue empty — cheap poll
            continue
        try:
            limiter.acquire()  # ANTHROPIC_MAX_CALLS_PER_10S token bucket
            if job.kind == "step_verdict":
                process_verdict(job, pool, anthropic, s3, cfg)
            elif job.kind == "localization":
                process_localization(job, pool, anthropic, cfg)
            else:
                raise ValueError(f"Unknown job kind: {job.kind}")
            queue.mark_done(pool, job)
        except Exception as exc:  # noqa: BLE001 — the queue owns retry semantics
            if job.attempts >= job.max_attempts:
                queue.mark_dead(pool, job, exc)  # stays in table for inspection
            else:
                queue.requeue(pool, job, exc, run_after=queue.backoff_deadline(job.attempts))


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s",
    )

    pool = ConnectionPool(cfg.database_url, min_size=2, max_size=cfg.concurrency + 2)
    limiter = TokenBucket(cfg.max_calls_per_10s)
    anthropic = Anthropic(api_key=cfg.anthropic_api_key)
    s3 = make_s3_client(cfg)

    log.info("starting %d worker threads (verdict=%s, escalation=%s)",
             cfg.concurrency, cfg.verdict_model, cfg.escalation_model)
    threads = [
        threading.Thread(
            target=work_loop, args=(pool, limiter, anthropic, s3, cfg),
            name=f"worker-{i}", daemon=True,
        )
        for i in range(cfg.concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
