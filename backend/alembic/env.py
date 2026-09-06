from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from airline_core.persistence.models import Base
from alembic import context

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Alembic's version table prevents divergent revisions but does not by
        # itself serialize two deployers. This PostgreSQL session advisory lock
        # spans the transaction and is released even when a migration fails.
        # AUTOCOMMIT keeps this session-level advisory lock outside Alembic's
        # DDL transaction. A normal SELECT here would otherwise start an
        # implicit transaction that gets rolled back on connection close.
        lock_connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        lock_connection.execute(
            sa.text("SELECT pg_advisory_lock(hashtext(:key))"), {"key": "airline:alembic-upgrade"}
        )
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        except Exception:
            connection.rollback()
            raise
        finally:
            lock_connection.execute(
                sa.text("SELECT pg_advisory_unlock(hashtext(:key))"),
                {"key": "airline:alembic-upgrade"},
            )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
