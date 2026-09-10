# Airline OLTP MVP

Transactional reservation engine and versioned FastAPI adapter for the course MVP. Python 3.12, SQLAlchemy 2.x and PostgreSQL 16 are the supported path. SQLite is deliberately unsupported because it cannot demonstrate `SELECT ... FOR UPDATE` semantics.

## Run locally

```bash
cd backend
python3 -m pip install -e '.[dev]'
docker compose up -d
export DATABASE_URL='postgresql+psycopg://airline:airline_local_only@localhost:54329/airline'
python3 -m airline_core.persistence.bootstrap --with-demo-data
PYTHONPATH=. python3 -m pytest -q
uvicorn airline_core.main:app --host 127.0.0.1 --port 8000
```

The last command starts the server and remains in the foreground; run it after the tests or in a separate terminal.

The local-only container exposes PostgreSQL on `localhost:54329`. Its credentials are intentionally development values in `docker-compose.yml`, not AWS or production credentials. Set `DATABASE_URL` to point tests/services at another PostgreSQL database if needed.

## Design boundaries

- `airline_core/domain`: pure policy (money, itinerary, lifecycle and stable domain errors).
- `airline_core/application`: `BookingService` and database-backed runtime policy.
- `airline_core/persistence`: SQLAlchemy mappings, database session factory and deterministic seed data.
- `airline_core/api.py`: typed `/api/v1` adapter, one SQLAlchemy transaction per request, stable errors and demo authorization.
- `alembic`: the only DDL authority. `0001` is an explicit historical snapshot, `0002`–`0005` evolve OLTP, and `0006`–`0007` add the isolated `analytics` schema and its refresh function.

`BookingService.create` locks each requested `Inventory` row with PostgreSQL `FOR UPDATE`, ordered by `(flight_leg_instance_id, cabin)`, rechecks capacity, then holds seats and inventory atomically. A partial unique index prevents simultaneous active assignment of the same physical seat for a leg. Released rows retain history, so a seat can be reused later.

All stored timestamps are UTC (`timestamptz`); airport records carry IANA zones and the API returns UTC plus local schedules. Monetary fields are `NUMERIC(14,2)` and pricing uses `Decimal` with `ROUND_HALF_UP`. Hold, quote, sale, cancellation, refund, fare, tax and commission rules are loaded from the seeded operational catalogs. Operations call `expire_due` during booking and search, and administration exposes the same cleanup operation, so correctness does not depend on a scheduler.

`idempotency_records` is authoritative for reservation replay during its 24-hour window. The similarly named reservation columns remain immutable request evidence for migration compatibility. Payments use their unique synthetic operation reference. See ADR-0003 for the complete decision.

## HTTP demo

Open `http://127.0.0.1:8000/` for the same-origin static client. OpenAPI is at `/docs` and the database healthcheck at `/api/v1/health`. The public workflow covers search, hold, lookup by locator plus surname, simulated payment, tickets/coupons, cancellation and expiration. Typed admin endpoints expose inventory, reservations, audit, settings, fare rules, airports, agencies and agents.

Default passenger requests use the persisted `demo-passenger` identity. Privileged demo calls must provide registered, active identities: `demo-admin`/`ADMIN`, `demo-airport`/`AIRPORT`, or `agent-7`/`AGENCY_AGENT` with `X-Demo-Agency-Id: agency-1`. These headers are deliberately demo-only and are not production authentication.

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

## Analytical data layer

The same PostgreSQL database now contains an isolated dimensional schema named
`analytics`. AWS Glue or the local runner invokes one versioned, transactional
refresh function; it loads reservation, passenger-segment sales and occupancy
facts without copying passenger PII. See
[`docs/analytics-architecture.md`](../docs/analytics-architecture.md),
[`docs/analytics-model.md`](../docs/analytics-model.md), and
[`docs/analytics-detailed-design.md`](../docs/analytics-detailed-design.md),
the source and preview [diagram catalog](../diagramas/README.md), and
[`analytics/README.md`](../analytics/README.md). Dashboards and business analysis
remain outside this phase.

## Limits intentionally outside this MVP

There is no production authentication, resource-level authorization, real payment gateway/card data, analytical dashboard, visual seat selection, partial cancellation, check-in, baggage, notification or flight change. Payment input accepts only simulated boolean approval and a synthetic operation reference; it stores no PAN/CVV. The AWS artifacts are deployment-ready but this repository preparation does not create AWS or IAM resources.
