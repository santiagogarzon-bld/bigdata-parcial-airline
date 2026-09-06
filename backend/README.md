# Airline core engine

Transactional, HTTP-independent reservation engine for the course MVP. Python 3.12, SQLAlchemy 2.x and PostgreSQL 16 are the supported path. SQLite is deliberately unsupported because it cannot demonstrate `SELECT ... FOR UPDATE` semantics.

## Run locally

```bash
cd backend
python3 -m pip install -e '.[dev]'
docker compose up -d
export DATABASE_URL='postgresql+psycopg://airline:airline_local_only@localhost:54329/airline'
python3 -m airline_core.persistence.bootstrap
PYTHONPATH=. python3 -m pytest -q
```

The local-only container exposes PostgreSQL on `localhost:54329`. Its credentials are intentionally development values in `docker-compose.yml`, not AWS or production credentials. Set `DATABASE_URL` to point tests/services at another PostgreSQL database if needed.

## Design boundaries

- `airline_core/domain`: pure policy (money, itinerary, lifecycle and stable domain errors).
- `airline_core/application`: `BookingService`, a synchronous transaction-oriented façade suitable for a later FastAPI adapter.
- `airline_core/persistence`: SQLAlchemy mappings, database session factory and deterministic seed data.
- `alembic`: the only DDL authority. `0001` is an explicit historical snapshot; `0002` and `0003` are forward migrations.

`BookingService.create` locks each requested `Inventory` row with PostgreSQL `FOR UPDATE`, ordered by `(flight_leg_instance_id, cabin)`, rechecks capacity, then holds seats and inventory atomically. A partial unique index prevents simultaneous active assignment of the same physical seat for a leg. Released rows retain history, so a seat can be reused later.

All timestamps are UTC (`timestamptz`); airport records carry IANA zones. Monetary fields are `NUMERIC(14,2)` and pricing uses `Decimal` with `ROUND_HALF_UP`. Holds are sixty minutes. Operations call `expire_due` as part of booking, so correctness does not depend on an external scheduler; a scheduler may invoke the same method as cleanup.

## Database bootstrap and operation

`python -m airline_core.persistence.bootstrap` is the one supported preparation command. It requires an explicit `DATABASE_URL`, rejects SQLite, template/maintenance databases and hostless targets, verifies PostgreSQL 14+, runs `alembic upgrade head`, then UPSERTs required non-PII catalogs. It never drops/truncates commercial tables. Add `--with-demo-data` only for synthetic BOG/MDE/CLO flights, seats, agency and last-seat fixtures.

Run the same command for a fresh database and for a database at `0001` or `0002`; migrations are transactional and Alembic takes a PostgreSQL session advisory lock named `airline:alembic-upgrade` so two deployers cannot upgrade concurrently. Re-running it updates natural-key catalog definitions and does not duplicate or delete reservations.

Before a production-like migration, take and verify a logical backup, for example `pg_dump --format=custom --file=airline-before-<date>.dump "$DATABASE_URL"`; restore to an isolated database with `pg_restore --clean --if-exists --dbname "$RESTORE_URL"`. Downgrade is intended for empty development/test databases only: `0003` removes its additive catalog/history tables, so production rollback is restore-from-backup rather than `alembic downgrade`.

Use separate PostgreSQL roles in a real deployment: a migrator owns/has DDL on the application schema; runtime only has `CONNECT`, schema `USAGE`, and DML on required tables/sequences. The local Docker lab uses one development role for simplicity and stores no production password. Do not expose the Docker port beyond localhost.

Troubleshooting: ensure `docker compose ps` is healthy; use `PYTHONPATH=.` when invoking the package without an editable install; a bootstrap exit code of 2 is target/connection validation and 3 is migration/seed failure. Do not use `create_all()` for deployment.

## Tests

```bash
# quick domain + PostgreSQL integration suite
python3 -m pytest -q

# real contention: default 1 iteration each for direct/two-segment
python3 -m pytest -q -m concurrency

# required stress profile: 30 iterations × 20 simultaneous requests for both cases
AIRLINE_CONCURRENCY_ITERATIONS=30 python3 -m pytest -q -m concurrency
```

The concurrent test uses independent PostgreSQL sessions and a barrier. It asserts exactly one winner, 19 inventory conflicts, zero remaining availability on the bottleneck, no duplicate physical seat and no partial reservation. It is intentionally configurable because the full 1,200-request profile can be slow in constrained CI.

## Limits intentionally left to later layers

There is no HTTP API, authentication, real payment gateway/card data, AWS/IAM/ETL, visual seat selection, partial cancellation, or flight change. Payment input accepts only simulated boolean approval and a synthetic operation reference; it stores no PAN/CVV. Administrative CRUD/search/manifest endpoints should call this model through a future adapter.
