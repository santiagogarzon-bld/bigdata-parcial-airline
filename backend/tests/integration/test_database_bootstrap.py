"""PostgreSQL-only evidence for fresh setup, reruns, upgrades, and schema contract."""

from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from airline_core.application.service import BookingService, CreateReservation, PassengerInput
from airline_core.domain.types import Cabin, Channel
from airline_core.persistence.bootstrap import bootstrap
from airline_core.persistence.models import (
    Airport,
    Base,
    CabinCatalog,
    FlightLegInstance,
    OperationalSetting,
    Reservation,
)
from alembic import command

pytestmark = pytest.mark.integration


def _reset_to_base() -> Config:
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    return config


def test_bootstrap_from_empty_and_idempotent_preserves_commercial_rows(pg_engine):
    _reset_to_base()
    url = pg_engine.url.render_as_string(hide_password=False)
    bootstrap(url, with_demo_data=True)
    assert set(inspect(pg_engine).get_table_names()) >= {
        "cabins",
        "fare_rules",
        "operational_settings",
        "inventories",
    }
    Session = sessionmaker(pg_engine, expire_on_commit=False)
    with Session.begin() as session:
        leg = session.scalar(select(FlightLegInstance).order_by(FlightLegInstance.departure_at))
        assert leg is not None
        reservation = BookingService(session).create(
            CreateReservation(
                actor_id="bootstrap-test",
                channel=Channel.DIRECT,
                idempotency_key="stable-row",
                leg_ids=(leg.id,),
                cabin=Cabin.ECONOMY,
                passengers=(PassengerInput("Synthetic", "Passenger"),),
            )
        )
        reservation_id = reservation.id
    bootstrap(url)
    with Session() as session:
        assert session.get(Reservation, reservation_id) is not None
        assert session.scalar(select(CabinCatalog).where(CabinCatalog.code == "ECONOMY"))
        assert session.scalar(
            select(OperationalSetting).where(OperationalSetting.key == "hold_minutes")
        )
        assert session.scalar(select(Airport).where(Airport.code == "BOG"))


@pytest.mark.parametrize("revision", ["0001_core_schema", "0002_idempotency_window"])
def test_each_legacy_revision_upgrades_without_losing_valid_reservation(pg_engine, revision):
    config = _reset_to_base()
    command.upgrade(config, revision)
    reservation_id = str(uuid4())
    scope_column = ", idempotency_scope" if revision == "0002_idempotency_window" else ""
    scope_value = ", :scope" if scope_column else ""
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO reservations
                (id, locator, state, cabin, channel, actor_id, expires_at,
                 idempotency_key, payload_hash, total, commission"""
                + scope_column
                + """ )
                VALUES (:id, 'UPGRADE1', 'PENDING_PAYMENT', 'ECONOMY', 'DIRECT',
                        'migration-test', now() + interval '2 hours', 'legacy-key',
                        :hash, 0, 0"""
                + scope_value
                + ")"
            ),
            {"id": reservation_id, "hash": "a" * 64, "scope": "legacy-key:old"},
        )
    command.upgrade(config, "head")
    with pg_engine.connect() as connection:
        assert (
            str(
                connection.scalar(
                    text("SELECT id FROM reservations WHERE id = :id"), {"id": reservation_id}
                )
            )
            == reservation_id
        )


def test_head_schema_contains_all_sqlalchemy_tables_and_critical_constraints(pg_engine):
    bootstrap(pg_engine.url.render_as_string(hide_password=False))
    inspector = inspect(pg_engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    inventory_checks = {item["name"] for item in inspector.get_check_constraints("inventories")}
    item_indexes = {item["name"] for item in inspector.get_indexes("reservation_items")}
    assert "ck_inventory_nonnegative" in inventory_checks
    assert "uq_active_seat_assignment" in item_indexes
