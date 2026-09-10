# Analytics ETL

`etl.py` is a thin local orchestrator for the set-based PostgreSQL ELT
function `analytics.refresh_warehouse(run_id, snapshot_at)`. The function is
the single transformation implementation and is owned by Alembic. Reruns are
deterministic when the optional run id and snapshot are supplied. Failed runs
are persisted in a separate transaction in `analytics.etl_run`, even when the
refresh transaction itself rolls back.

The loader contains no passenger, actor, agent, or other PII. Local production
runs use separate source and target URLs. AWS Glue uses its two named JDBC
connections to resolve the independent source and target RDS endpoints, creates
transaction-scoped foreign tables, then invokes the function
through the JVM PostgreSQL JDBC driver.

```bash
python analytics/bootstrap_warehouse.py --target-database-url "$TARGET_DATABASE_URL"
python -m analytics.etl --source-database-url "$SOURCE_DATABASE_URL" \
  --target-database-url "$TARGET_DATABASE_URL"
```

The target is an independent RDS database with no operational `public` tables
and no persistent foreign server. The bootstrap reuses analytical migrations
0006/0007 without installing OLTP.
Glue uses `glue_job.py`, which invokes the versioned database-side refresh
through Spark's JVM JDBC driver and does not require `psycopg` or network
package installs. It also records failures after rollback in a separate JDBC
transaction.

Run its isolated checks from the repository root with
`python -m pytest -q analytics/tests`.
