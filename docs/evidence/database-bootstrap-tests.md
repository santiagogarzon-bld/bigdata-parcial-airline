# Database hardening evidence

Executed locally against Docker PostgreSQL 16 on 2026-09-09.

```text
$ cd backend
$ ruff check airline_core alembic tests
All checks passed!
$ mypy airline_core
Success: no issues found in 12 source files
$ PYTHONPATH=. pytest -q --cov=airline_core.domain --cov=airline_core.application
15 passed in 10.48s
Required test coverage of 90.0% reached. Total coverage: 92.48%
$ AIRLINE_CONCURRENCY_ITERATIONS=1 PYTHONPATH=. pytest -q -m concurrency
2 passed, 13 deselected in 1.87s
```

The suite covers a fresh `base → head → bootstrap --with-demo-data` run, a second bootstrap preserving a synthetic reservation, upgrades from `0001_core_schema` and `0002_idempotency_window` while retaining a valid reservation row, metadata/table plus critical-constraint contract, ordinary booking integration, and real PostgreSQL 20-client concurrency (one default iteration per direct and connection case).

The full 30×20 contention profile was executed after the initial suite:

```text
AIRLINE_CONCURRENCY_ITERATIONS=30 PYTHONPATH=. pytest -q -m concurrency
2 passed, 13 deselected in 41.66s
DURATION_SECONDS=42
```

It executed two scenarios (direct and two-segment bottleneck), each with 30 runs
of 20 simultaneous requests: 1,200 requests total. Every run had one winner and
19 controlled inventory conflicts, as asserted by the test.

Secret scan executed from the repository root:

```text
rg -n -i -e 'vockey' -e 'x-amz-' -e 'akia[0-9a-z]{16}' -e 'asia[0-9a-z]{16}' \
  -e 'aws(_|-)?secret(_|-)?access(_|-)?key' -e 'aws(_|-)?access(_|-)?key(_|-)?id' \
  -e 'begin ([a-z ]+ )?private key' -e 'secret_access_key' ...
```

There were three matches, all in `docs/01-definicion-del-proyecto.md`; they are
policy text documenting that an omitted `vockey` signed URL must not be stored.
No credential, signed URL, AWS access key, secret access key, or private key was found.
