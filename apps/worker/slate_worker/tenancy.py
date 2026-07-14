"""Per-job tenant context for RLS (§9 pool-reset warning).

Workers set the org with TRANSACTION-scoped set_config(..., true) — it
auto-resets on commit/rollback, so a pooled connection can never carry a stale
org_id to the next job.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from psycopg import Connection
from psycopg_pool import ConnectionPool


@contextmanager
def org_transaction(pool: ConnectionPool, org_id: UUID):
    """One transaction with app.current_org_id set; all tenant-table access for
    a job must happen inside this block."""
    with pool.connection() as conn:  # commits on clean exit, rolls back on error
        conn.execute("SELECT set_config('app.current_org_id', %s, true)", (str(org_id),))
        yield conn


__all__ = ["org_transaction", "Connection"]
