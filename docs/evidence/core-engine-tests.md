# Core engine test evidence

Recorded locally on 2026-09-09, Linux, Python 3.12.3, PostgreSQL 16 (`postgres:16-alpine` in Docker Compose), SQLAlchemy 2.0.42. The database was the local disposable container at `localhost:54329`; no SQLite, AWS, credentials, or mocks were used for lock semantics.

## Schema / seeds

```text
$ cd backend
$ docker compose up -d
Container backend-postgres-1 Running
$ python3 -m alembic upgrade head
$ python3 -m airline_core.persistence.seed_cli
```

The integration suite includes `test_migration_from_scratch`, which executes Alembic downgrade-to-base and upgrade-to-head and asserts the core tables.

## Full unit and integration run

```text
$ python3 -m pytest --cov=airline_core.domain --cov=airline_core.application --cov-report=term-missing -q
..........                                                               [100%]
11 passed in 4.61s
Required test coverage of 90.0% reached. Total coverage: 92.35%
```

The coverage configuration intentionally scopes the 90% threshold to domain/application code. Migrations, declarative mappings, seed fixtures, and configuration are excluded because their behavioral proof is integration migration/constraint testing rather than branch coverage.

## Full real concurrency profile

```text
$ AIRLINE_CONCURRENCY_ITERATIONS=30 python3 -m pytest -q -m concurrency
..                                                                       [100%]
2 passed, 9 deselected in 27.85s
```

Each of the two parametrized cases (direct and two-segment with the second segment as bottleneck) runs 30 iterations of 20 concurrent independent PostgreSQL sessions: 1,200 requests total. Every iteration asserts one winner, 19 `INVENTORY_UNAVAILABLE` conflicts, bottleneck availability zero, no duplicate active physical seat, and no partial reservation.

## Static quality gates

```text
$ ruff check airline_core tests
All checks passed!
$ mypy airline_core
Success: no issues found in 11 source files
```
