# Analytics ETL

`etl.py` is a thin local orchestrator for the set-based PostgreSQL ELT
function `analytics.refresh_warehouse(run_id, snapshot_at)`. The function is
the single transformation implementation and is owned by Alembic. Reruns are
deterministic when the optional run id and snapshot are supplied. Failed runs
are persisted in a separate transaction in `analytics.etl_run`, even when the
refresh transaction itself rolls back.

The loader contains no passenger, actor, agent, or other PII. It is suitable
for a local run with one `DATABASE_URL`. AWS Glue uses its two named JDBC
connections only to resolve the same RDS endpoint, then invokes the function
through the JVM PostgreSQL JDBC driver.

```bash
DATABASE_URL='postgresql://...' \
python -m analytics.etl
```

The target is the same PostgreSQL RDS database as the source in this academic
deployment; the source
tables are in `public` and the destination is `analytics`. Alembic owns the
schema DDL and refresh function; apply migrations through
`0007_analytics_refresh` before running the loader.
Glue uses `glue_job.py`, which invokes the versioned database-side refresh
through Spark's JVM JDBC driver and does not require `psycopg` or network
package installs. It also records failures after rollback in a separate JDBC
transaction.

Run its isolated checks from the repository root with
`python -m pytest -q analytics/tests`.
