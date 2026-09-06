import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command

pytestmark = pytest.mark.integration


def test_migration_from_scratch(pg_engine):
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    names = set(inspect(pg_engine).get_table_names())
    assert {"inventories", "reservations", "reservation_items", "tickets", "audit_events"} <= names
