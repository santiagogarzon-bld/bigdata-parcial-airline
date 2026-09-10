from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from airline_core.application.service import BookingService
from alembic import command as alembic_command

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def migrated_analytics_schema(pg_engine):
    """Make this module reproducible against a PostgreSQL database at any revision."""
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", pg_engine.url.render_as_string(hide_password=False))
    alembic_command.upgrade(config, "head")


def test_analytics_schema_contract(pg_engine):
    """The analytical migration exposes all expected facts, dimensions and controls."""
    inspector = inspect(pg_engine)
    assert "analytics" in inspector.get_schema_names()
    tables = set(inspector.get_table_names(schema="analytics"))
    assert {
        "dim_date",
        "dim_route",
        "dim_flight",
        "dim_cabin",
        "dim_fare_band",
        "dim_channel",
        "dim_agency",
        "fact_sales_segment",
        "fact_reservation",
        "fact_leg_occupancy",
        "etl_run",
        "etl_watermark",
    } <= tables

    sales_columns = {
        column["name"] for column in inspector.get_columns("fact_sales_segment", schema="analytics")
    }
    assert {
        "source_reservation_item_id",
        "gross_amount",
        "approved_revenue",
        "refund_amount",
        "net_revenue",
        "booking_date_key",
        "departure_date_key",
        "fare_band_key",
        "route_key",
    } <= sales_columns
    reservation_columns = {
        column["name"] for column in inspector.get_columns("fact_reservation", schema="analytics")
    }
    assert {
        "previously_confirmed",
        "cancellation_date_key",
        "departure_date_key",
        "advance_days",
    } <= reservation_columns
    fare_columns = {
        column["name"] for column in inspector.get_columns("dim_fare_band", schema="analytics")
    }
    assert {"min_days_before_departure", "max_days_before_departure"} <= fare_columns
    assert "bridge_reservation_route" in tables
    occupancy_columns = {
        column["name"] for column in inspector.get_columns("fact_leg_occupancy", schema="analytics")
    }
    assert {
        "capacity",
        "confirmed",
        "available",
        "occupancy_ratio",
        "snapshot_at",
    } <= occupancy_columns
    forbidden_pii = {"given_name", "surname", "locator", "actor_id", "agent_id", "idempotency_key"}
    for table in tables:
        columns = {column["name"] for column in inspector.get_columns(table, schema="analytics")}
        assert forbidden_pii.isdisjoint(columns), f"PII leaked into analytics.{table}"


def test_analytics_occupancy_generated_columns(pg_engine):
    """Generated availability and ratio remain consistent with source measures."""
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text(
                "INSERT INTO analytics.dim_date VALUES (20260910, '2026-09-10', 2026, 3, 9, 37, 10, 4) ON CONFLICT DO NOTHING"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analytics.dim_route(source_route_id, route_code, origin, destination) VALUES (:id, :code, 'BOG', 'MDE')"
            ),
            {"id": str(uuid4()), "code": f"TEST-{uuid4().hex[:12]}"},
        )
        connection.execute(
            text(
                "INSERT INTO analytics.dim_flight(source_flight_instance_id, flight_number, service_date, flight_state) VALUES (:id, :number, '2026-09-10', 'SCHEDULED')"
            ),
            {"id": str(uuid4()), "number": f"T{uuid4().hex[:8]}"},
        )
        connection.execute(
            text(
                "INSERT INTO analytics.dim_cabin(cabin_code, display_name) VALUES (:code, 'Test')"
            ),
            {"code": f"TEST-{uuid4().hex[:8]}"},
        )
        route = connection.execute(
            text("SELECT route_key FROM analytics.dim_route ORDER BY route_key DESC LIMIT 1")
        ).scalar_one()
        flight = connection.execute(
            text("SELECT flight_key FROM analytics.dim_flight ORDER BY flight_key DESC LIMIT 1")
        ).scalar_one()
        cabin = connection.execute(
            text("SELECT cabin_key FROM analytics.dim_cabin ORDER BY cabin_key DESC LIMIT 1")
        ).scalar_one()
        connection.execute(
            text("""
            INSERT INTO analytics.fact_leg_occupancy
              (source_inventory_id, snapshot_at, departure_date_key, route_key, flight_key, cabin_key, capacity, held, confirmed)
            VALUES ('00000000-0000-0000-0000-000000000002', now(), 20260910, :route, :flight, :cabin, 100, 5, 45)
        """),
            {"route": route, "flight": flight, "cabin": cabin},
        )
        available, ratio = connection.execute(
            text(
                "SELECT available, occupancy_ratio FROM analytics.fact_leg_occupancy ORDER BY occupancy_key DESC LIMIT 1"
            )
        ).one()
        assert available == 50
        assert float(ratio) == pytest.approx(0.45)
        transaction.rollback()


def test_refresh_confirmed_multileg_cancel_and_rerun(session, command):
    """Refresh is set-based: approved revenue is loaded, cancellation updates in place."""
    service = BookingService(session)
    reservation = service.create(command(f"analytics-{uuid4().hex[:12]}", two=True))
    session.commit()
    service.process_payment(reservation.id, f"analytics-pay-{uuid4().hex}", True)
    session.commit()
    run_id = str(uuid4())
    snapshot = datetime.now(UTC)
    session.execute(
        text("SELECT analytics.refresh_warehouse(:run_id, :snapshot)"),
        {"run_id": run_id, "snapshot": snapshot},
    )
    session.commit()

    before = session.execute(
        text("""
        SELECT count(*), sum(approved_revenue), sum(refund_amount), sum(net_revenue)
        FROM analytics.fact_sales_segment WHERE source_reservation_id = :reservation_id
    """),
        {"reservation_id": reservation.id},
    ).one()
    routes_before = session.execute(
        text("""
        SELECT count(*) FROM analytics.bridge_reservation_route b
        JOIN analytics.fact_reservation f ON f.reservation_key = b.reservation_key
        WHERE f.source_reservation_id = :reservation_id
    """),
        {"reservation_id": reservation.id},
    ).scalar_one()
    assert before[0] == 2 and before[1] > 0 and before[2] == 0 and before[3] == before[1]
    assert routes_before == 2

    service.cancel(reservation.id, "guest")
    session.commit()
    cancel_run_id = str(uuid4())
    cancel_snapshot = datetime.now(UTC)
    session.execute(
        text("SELECT analytics.refresh_warehouse(:run_id, :snapshot)"),
        {"run_id": cancel_run_id, "snapshot": cancel_snapshot},
    )
    session.commit()
    run_audit = session.execute(
        text("""
        SELECT status, reconciliation->>'source_reservations',
               reconciliation->>'target_reservations',
               reconciliation->>'approved_delta', reconciliation->>'refund_delta'
        FROM analytics.etl_run WHERE run_id = :run_id
    """),
        {"run_id": cancel_run_id},
    ).one()
    assert run_audit[0] == "SUCCEEDED"
    assert run_audit[1] == run_audit[2]
    assert run_audit[3:] == ("0.00", "0.00")
    session.execute(
        text("SELECT analytics.refresh_warehouse(:run_id, :snapshot)"),
        {"run_id": cancel_run_id, "snapshot": cancel_snapshot},
    )
    session.commit()
    after = session.execute(
        text("""
        SELECT reservation_state, previously_confirmed, cancellation_flag, cancellation_at,
               (SELECT count(*) FROM analytics.fact_sales_segment WHERE source_reservation_id = :reservation_id)
        FROM analytics.fact_reservation WHERE source_reservation_id = :reservation_id
    """),
        {"reservation_id": reservation.id},
    ).one()
    assert after[0] == "CANCELLED" and after[1] is True and after[2] is True
    assert after[3] is not None and after[4] == 2
    after_sales = session.execute(
        text("""
        SELECT sum(approved_revenue), sum(refund_amount), sum(net_revenue), count(*)
        FROM analytics.fact_sales_segment WHERE source_reservation_id = :reservation_id
    """),
        {"reservation_id": reservation.id},
    ).one()
    source_refund = session.execute(
        text("""
        SELECT COALESCE(sum(amount), 0) FROM public.refunds WHERE reservation_id = :reservation_id
    """),
        {"reservation_id": reservation.id},
    ).scalar_one()
    assert after_sales[0] == before[1] and after_sales[1] == source_refund
    assert after_sales[2] == after_sales[0] - after_sales[1] and after_sales[3] == 2
    assert (
        session.execute(
            text("""
        SELECT count(*) FROM analytics.fact_leg_occupancy
        WHERE snapshot_at = :snapshot
    """),
            {"snapshot": cancel_snapshot},
        ).scalar_one()
        == session.execute(text("SELECT count(*) FROM public.inventories")).scalar_one()
    )
    with pytest.raises(DBAPIError):
        session.execute(
            text("SELECT analytics.refresh_warehouse(:run_id, :snapshot)"),
            {"run_id": cancel_run_id, "snapshot": datetime.now(UTC)},
        )
    session.rollback()
    assert (
        session.execute(
            text("SELECT status FROM analytics.etl_run WHERE run_id = :run_id"),
            {"run_id": cancel_run_id},
        ).scalar_one()
        == "SUCCEEDED"
    )


def test_refresh_distinguishes_cancelled_failed_and_expired(session, command):
    """Only an explicit cancellation contributes to the cancellation fact flag."""
    service = BookingService(session)

    cancelled = service.create(command(f"analytics-pending-cancel-{uuid4().hex[:8]}"))
    session.commit()
    service.cancel(cancelled.id, "guest")
    session.commit()

    failed = service.create(command(f"analytics-declined-{uuid4().hex[:8]}"))
    session.commit()
    service.process_payment(failed.id, f"analytics-decline-{uuid4().hex}", False)
    session.commit()

    expired = service.create(command(f"analytics-expired-{uuid4().hex[:8]}"))
    session.commit()
    future_service = BookingService(
        session, clock=lambda: expired.expires_at + timedelta(seconds=1)
    )
    assert future_service.expire_due() == 1
    session.commit()

    session.execute(
        text("SELECT analytics.refresh_warehouse(:run_id, :snapshot)"),
        {"run_id": str(uuid4()), "snapshot": datetime.now(UTC)},
    )
    session.commit()

    rows = {
        str(row.source_reservation_id): (
            row.reservation_state,
            row.cancellation_flag,
            row.previously_confirmed,
        )
        for row in session.execute(
            text(
                """SELECT source_reservation_id, reservation_state,
                          cancellation_flag, previously_confirmed
                   FROM analytics.fact_reservation
                   WHERE source_reservation_id IN (:cancelled, :failed, :expired)"""
            ),
            {"cancelled": cancelled.id, "failed": failed.id, "expired": expired.id},
        )
    }
    assert rows[cancelled.id] == ("CANCELLED", True, False)
    assert rows[failed.id] == ("PAYMENT_FAILED", False, False)
    assert rows[expired.id] == ("EXPIRED", False, False)
