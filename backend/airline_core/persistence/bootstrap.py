"""Safe database preparation command: migration first, catalog seed second."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from alembic import command

from .seeds import seed_demo, seed_parameters

MIN_POSTGRES_MAJOR = 14


class BootstrapError(Exception):
    """An expected, user-actionable bootstrap failure."""


def database_url_from_environment() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise BootstrapError("DATABASE_URL is required; refusing to select an implicit target")
    url = make_url(value)
    _validate_url(url)
    return value


def _validate_url(url: URL) -> None:
    if url.get_backend_name() != "postgresql":
        raise BootstrapError(
            "DATABASE_URL must target PostgreSQL; SQLite and other engines are rejected"
        )
    if not url.database or url.database in {"postgres", "template0", "template1"}:
        raise BootstrapError("refusing a maintenance/template database target")
    if not url.host:
        raise BootstrapError("DATABASE_URL must name a PostgreSQL host explicitly")


def _alembic_config(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _check_postgres(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            version = int(connection.scalar(text("SHOW server_version_num")) or 0)
    except SQLAlchemyError as error:
        raise BootstrapError(f"cannot connect to PostgreSQL: {error.__class__.__name__}") from error
    finally:
        engine.dispose()
    if version < MIN_POSTGRES_MAJOR * 10000:
        raise BootstrapError(
            f"PostgreSQL {MIN_POSTGRES_MAJOR}+ is required (server_version_num={version})"
        )


def bootstrap(url: str, with_demo_data: bool = False) -> None:
    _validate_url(make_url(url))
    _check_postgres(url)
    command.upgrade(_alembic_config(url), "head")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        Session = sessionmaker(engine, expire_on_commit=False)
        with Session.begin() as session:
            seed_parameters(session)
            if with_demo_data:
                seed_demo(session)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade PostgreSQL and load idempotent airline catalogs"
    )
    parser.add_argument(
        "--with-demo-data", action="store_true", help="also load synthetic demo flights"
    )
    args = parser.parse_args(argv)
    try:
        bootstrap(database_url_from_environment(), args.with_demo_data)
    except BootstrapError as error:
        print(f"bootstrap rejected: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - stable CLI code wraps Alembic's exception hierarchy.
        print(f"bootstrap failed: {error}", file=sys.stderr)
        return 3
    print(
        "bootstrap complete: schema=head, parameters=upserted"
        + (", demo=upserted" if args.with_demo_data else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
