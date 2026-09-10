"""Local entrypoint for the versioned PostgreSQL analytical refresh."""

from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg


def _safe_error(error: Exception) -> str:
    return f"ETL_REFRESH_FAILED:{type(error).__name__}"[:200]


def run(
    connection: Any,
    *,
    run_id: uuid.UUID | str | None = None,
    snapshot_at: datetime | None = None,
) -> str:
    """Invoke one atomic refresh and return its auditable run identifier."""
    rid = str(run_id or uuid.uuid4())
    snapshot = snapshot_at or datetime.now(timezone.utc)
    try:
        with connection.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("SELECT to_regnamespace('analytics')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("analytics schema is missing; apply Alembic first")
            cur.execute(
                "SELECT * FROM analytics.refresh_warehouse(%s::uuid, %s::timestamptz)",
                (rid, snapshot),
            )
            cur.fetchone()
        connection.commit()
        return rid
    except Exception as error:
        connection.rollback()
        # The refresh transaction may have rolled back its own RUNNING row.
        # Persist failure in a separate transaction so operators can reconcile.
        try:
            with connection.cursor() as failure_cursor:
                failure_cursor.execute(
                    """INSERT INTO analytics.etl_run
                    (run_id, pipeline_name, started_at, finished_at, source_cutoff_at,
                     status, error_message)
                    VALUES (%s::uuid, 'warehouse_refresh', now(), now(), %s,
                            'FAILED', %s)
                    ON CONFLICT (run_id) DO UPDATE SET finished_at=EXCLUDED.finished_at,
                      status='FAILED', error_message=EXCLUDED.error_message
                      WHERE analytics.etl_run.status <> 'SUCCEEDED'""",
                    (rid, snapshot, _safe_error(error)),
                )
            connection.commit()
        except Exception:  # noqa: BLE001 - never mask the original refresh failure
            connection.rollback()
        raise


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description="Run the PostgreSQL analytics refresh")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        required=not os.getenv("DATABASE_URL"),
    )
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--snapshot-at", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    with psycopg.connect(args.database_url) as connection:
        result = run(connection, run_id=args.run_id, snapshot_at=args.snapshot_at)
    print(f"analytics refresh succeeded: run_id={result}")
    return result


if __name__ == "__main__":
    main()
