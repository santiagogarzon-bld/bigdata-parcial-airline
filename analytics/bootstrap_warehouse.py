"""Create only the analytical objects in an independent PostgreSQL database."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "backend/alembic/versions/0006_analytics_schema.py",
    ROOT / "backend/alembic/versions/0007_analytics_refresh.py",
)


class _Executor:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load analytical migration {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bootstrap(connection: Any) -> None:
    """Apply only 0006/0007 without creating any OLTP application tables."""
    for path in MIGRATIONS:
        module = _load(path)
        module.op = _Executor(connection)
        module.upgrade()
    connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-database-url", default=os.getenv("TARGET_DATABASE_URL"))
    args = parser.parse_args()
    if not args.target_database_url:
        parser.error("provide --target-database-url")
    with psycopg.connect(args.target_database_url) as connection:
        bootstrap(connection)
    print("independent analytics database bootstrapped")


if __name__ == "__main__":
    main()
