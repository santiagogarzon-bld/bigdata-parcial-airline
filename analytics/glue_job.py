"""AWS Glue 4 Spark entrypoint.

The warehouse refresh is intentionally a database-side, versioned procedure:
Glue supplies connectivity and orchestration while PostgreSQL performs the
atomic ELT.  This avoids assuming ``psycopg`` or PyPI access in Glue workers.
"""

import uuid
import re
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext


def _safe_error(error: Exception) -> str:
    return f"ETL_REFRESH_FAILED:{type(error).__name__}"[:200]


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    args = getResolvedOptions(
        __import__("sys").argv,
        [
            "JOB_NAME",
            "source_connection_name",
            "target_connection_name",
            "source_catalog_database",
            "target_catalog_database",
            "target_schema",
        ],
    )
    context = GlueContext(SparkContext.getOrCreate())
    job = Job(context)
    job.init(args["JOB_NAME"], args)
    # The connections intentionally reference different private RDS instances.
    source = context.extract_jdbc_conf(args["source_connection_name"])
    target = context.extract_jdbc_conf(args["target_connection_name"])
    source_url = source.get("fullUrl") or source.get("url")
    target_url = target.get("fullUrl") or target.get("url")
    if source_url == target_url:
        raise RuntimeError("source and target must be different PostgreSQL databases")
    if args["target_schema"] != "analytics":
        raise RuntimeError("target_schema must be analytics")
    run_id = str(uuid.uuid4())
    snapshot = datetime.now(timezone.utc).isoformat()
    # Use a real JDBC transaction; Spark's query option is not guaranteed to
    # permit a side-effecting function call or to expose commit/rollback.
    jdbc = context.spark_session.sparkContext._jvm.java.sql
    conn = jdbc.DriverManager.getConnection(
        target_url, target.get("user", ""), target.get("password", "")
    )
    try:
        conn.setAutoCommit(False)
        conn.setTransactionIsolation(jdbc.Connection.TRANSACTION_REPEATABLE_READ)
        match = re.match(r"jdbc:postgresql://([^:/]+):(\d+)/([^?]+)", source_url or "")
        if not match:
            raise RuntimeError("invalid source PostgreSQL JDBC URL")
        host, port, database = match.groups()
        ddl = conn.createStatement()
        ddl.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
        ddl.execute(
            "CREATE SERVER airline_etl_source FOREIGN DATA WRAPPER postgres_fdw OPTIONS ("
            f"host {_literal(host)}, port {_literal(port)}, dbname {_literal(database)}, "
            "sslmode 'require')"
        )
        ddl.execute(
            "CREATE USER MAPPING FOR CURRENT_USER SERVER airline_etl_source OPTIONS ("
            f"user {_literal(source.get('user', ''))}, "
            f"password {_literal(source.get('password', ''))})"
        )
        ddl.execute(
            "IMPORT FOREIGN SCHEMA public LIMIT TO (agencies, audit_events, cabins, "
            "flight_instances, flight_leg_instances, inventories, payments, refunds, "
            "reservation_items, reservations, scheduled_flights, scheduled_legs) "
            "FROM SERVER airline_etl_source INTO public"
        )
        statement = conn.prepareStatement(
            "SELECT * FROM analytics.refresh_warehouse(?::uuid, ?::timestamptz)"
        )
        statement.setString(1, run_id)
        statement.setString(2, snapshot)
        statement.executeQuery().close()
        ddl.execute("DROP SERVER airline_etl_source CASCADE")
        conn.commit()
        print(f"analytics refresh succeeded: run_id={run_id}")
    except Exception as error:
        conn.rollback()
        # Persist outside the failed refresh transaction; the function's own
        # etl_run write can have been rolled back with the data transaction.
        try:
            failed = conn.prepareStatement("""INSERT INTO analytics.etl_run
                (run_id, pipeline_name, started_at, finished_at, source_cutoff_at,
                 status, error_message)
                VALUES (?::uuid, 'warehouse_refresh', now(), now(),
                        ?::timestamptz, 'FAILED', ?)
                ON CONFLICT (run_id) DO UPDATE SET finished_at=EXCLUDED.finished_at,
                  status='FAILED', error_message=EXCLUDED.error_message
                  WHERE analytics.etl_run.status <> 'SUCCEEDED'""")
            failed.setString(1, run_id)
            failed.setString(2, snapshot)
            failed.setString(3, _safe_error(error))
            failed.executeUpdate()
            conn.commit()
        except Exception:  # noqa: BLE001 - never mask the original refresh failure
            conn.rollback()
        raise
    finally:
        conn.close()
    job.commit()


if __name__ == "__main__":
    main()
