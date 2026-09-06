# ADR-0002: Alembic migrations, guarded bootstrap, and operational catalogs

Status: accepted

## Decision

Alembic is the sole DDL authority. Revision `0001` was corrected before publication: it is now an explicit snapshot of the original DDL rather than importing mutable ORM metadata. This repository has no published/applied project baseline (the working tree was untracked when this decision was made); its resulting historical schema is preserved. `0002` and `0003_operational_schema` are forward upgrades.

The bootstrap command requires an explicit PostgreSQL 14+ `DATABASE_URL`, acquires the migration advisory lock through Alembic, upgrades to head, and UPSERTs parameter catalogs. Demo data is separate and only loads with `--with-demo-data`. No bootstrap action drops or truncates business tables.

Cabin/state values remain constrained strings rather than PostgreSQL enums: domain `StrEnum` values and named `CHECK`s are the single versionable source, avoiding enum deployment coupling. `cabins`, fare rules, and operational settings are data catalogs with natural stable keys.

## Consequences

DDL upgrades are transactional and two migrators serialize on `airline:alembic-upgrade`. The additive downgrade is for disposable databases only because it removes catalog/history additions; operational rollback is backup restore. PostgreSQL runtime and migrator roles should be separated, although the local lab intentionally uses a single non-production Docker role.
