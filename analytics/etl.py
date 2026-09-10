"""Local entrypoint for the versioned PostgreSQL analytical refresh."""

from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

SOURCE_TABLES = (
    "agencies", "audit_events", "cabins", "flight_instances",
    "flight_leg_instances", "inventories", "payments", "refunds",
    "reservation_items", "reservations", "scheduled_flights", "scheduled_legs",
)


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


def run_between_databases(
    target_connection: Any,
    source_database_url: str,
    *,
    run_id: uuid.UUID | str | None = None,
    snapshot_at: datetime | None = None,
) -> str:
    """Refresh an isolated OLAP database through transaction-scoped FDW tables."""
    source = conninfo_to_dict(source_database_url)
    required = ("host", "port", "dbname", "user", "password")
    missing = [key for key in required if not source.get(key)]
    if missing:
        raise ValueError(f"source database URL is missing: {', '.join(missing)}")
    rid = str(run_id or uuid.uuid4())
    snapshot = snapshot_at or datetime.now(timezone.utc)
    server_name = "airline_etl_source"
    try:
        with target_connection.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("SELECT to_regnamespace('analytics')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("analytics schema is missing; bootstrap OLAP first")
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
            cur.execute(
                sql.SQL("CREATE SERVER {} FOREIGN DATA WRAPPER postgres_fdw OPTIONS "
                        "(host {}, port {}, dbname {}, sslmode 'require')").format(
                    sql.Identifier(server_name), sql.Literal(source["host"]),
                    sql.Literal(source["port"]), sql.Literal(source["dbname"]),
                )
            )
            cur.execute(
                sql.SQL("CREATE USER MAPPING FOR CURRENT_USER SERVER {} OPTIONS "
                        "(user {}, password {})").format(
                    sql.Identifier(server_name), sql.Literal(source["user"]),
                    sql.Literal(source["password"]),
                )
            )
            table_list = sql.SQL(", ").join(map(sql.Identifier, SOURCE_TABLES))
            cur.execute(
                sql.SQL("IMPORT FOREIGN SCHEMA public LIMIT TO ({}) FROM SERVER {} INTO public").format(
                    table_list, sql.Identifier(server_name)
                )
            )
            cur.execute(
                "SELECT * FROM analytics.refresh_warehouse(%s::uuid, %s::timestamptz)",
                (rid, snapshot),
            )
            cur.fetchone()
            # CASCADE removes only the transaction-scoped foreign tables and mapping.
            cur.execute(sql.SQL("DROP SERVER {} CASCADE").format(sql.Identifier(server_name)))
        target_connection.commit()
        return rid
    except Exception:
        target_connection.rollback()
        raise


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description="Run the PostgreSQL analytics refresh")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="Legacy same-database mode")
    parser.add_argument("--source-database-url", default=os.getenv("SOURCE_DATABASE_URL"))
    parser.add_argument("--target-database-url", default=os.getenv("TARGET_DATABASE_URL"))
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--snapshot-at", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    if args.source_database_url and args.target_database_url:
        with psycopg.connect(args.target_database_url) as connection:
            result = run_between_databases(
                connection, args.source_database_url,
                run_id=args.run_id, snapshot_at=args.snapshot_at,
            )
    elif args.database_url:
        with psycopg.connect(args.database_url) as connection:
            result = run(connection, run_id=args.run_id, snapshot_at=args.snapshot_at)
    else:
        parser.error("provide --source-database-url and --target-database-url")
    print(f"analytics refresh succeeded: run_id={result}")
    return result


if __name__ == "__main__":
    main()
