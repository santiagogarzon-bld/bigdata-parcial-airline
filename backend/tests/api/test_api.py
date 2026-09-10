"""Acceptance tests for the HTTP adapter against real PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from airline_core.api import app, get_db
from airline_core.main import app as production_app
from airline_core.persistence.database import SessionLocal, database_url
from airline_core.persistence.models import (
    AuditEvent,
    Coupon,
    FlightLegInstance,
    IdempotencyRecord,
    Inventory,
    Itinerary,
    ItinerarySegment,
    Passenger,
    Payment,
    Refund,
    Reservation,
    ReservationItem,
    Ticket,
)
from airline_core.persistence.seeds import seed

ADMIN = {"X-Demo-Actor-Id": "demo-admin", "X-Demo-Role": "ADMIN"}
AIRPORT = {"X-Demo-Actor-Id": "demo-airport", "X-Demo-Role": "AIRPORT"}
AGENT = {
    "X-Demo-Actor-Id": "agent-7",
    "X-Demo-Role": "AGENCY_AGENT",
    "X-Demo-Agency-Id": "agency-1",
}


@dataclass
class ApiHarness:
    client: TestClient
    sessions: Any


@pytest.fixture(scope="session")
def pg_engine():
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL required")
    return engine


@pytest.fixture
def api(pg_engine):
    """Keep all request commits inside a savepoint-backed outer test transaction."""
    connection = pg_engine.connect()
    outer = connection.begin()
    sessions = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    with sessions.begin() as db:
        for model in (
            Refund,
            Coupon,
            Ticket,
            Payment,
            AuditEvent,
            ReservationItem,
            ItinerarySegment,
            Itinerary,
            Passenger,
            IdempotencyRecord,
            Reservation,
        ):
            db.execute(delete(model))
        db.execute(update(Inventory).values(held=0, confirmed=0))
        seed(db)

    original_options = dict(SessionLocal.kw)
    SessionLocal.configure(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield ApiHarness(client, sessions)
    finally:
        SessionLocal.kw.clear()
        SessionLocal.kw.update(original_options)
        outer.rollback()
        connection.close()


def _date_for(harness: ApiHarness, origin: str = "BOG") -> str:
    with harness.sessions() as db:
        departure = db.scalar(
            select(FlightLegInstance.departure_at)
            .where(
                FlightLegInstance.origin == origin,
                FlightLegInstance.departure_at > datetime.now(UTC) + timedelta(hours=25),
            )
            .order_by(FlightLegInstance.departure_at)
        )
    assert departure is not None
    return departure.astimezone(ZoneInfo("America/Bogota")).date().isoformat()


def _search(
    harness: ApiHarness,
    destination: str = "MDE",
    **overrides: Any,
):
    params = {
        "origin": "bog",
        "destination": destination.lower(),
        "date": _date_for(harness),
        "passengers": 1,
        "cabin": "ECONOMY",
        "max_stops": 1,
        **overrides,
    }
    return harness.client.get("/api/v1/flights/search", params=params)


def _booking_body(leg_ids: list[str], surname: str = "Tester") -> dict[str, Any]:
    return {
        "leg_ids": leg_ids,
        "cabin": "ECONOMY",
        "passengers": [{"given_name": "Http", "surname": surname}],
        "channel": "DIRECT",
    }


def _create(
    harness: ApiHarness,
    *,
    surname: str = "Tester",
    destination: str = "MDE",
    key: str | None = None,
) -> dict[str, Any]:
    search = _search(harness, destination)
    assert search.status_code == 200 and search.json()
    response = harness.client.post(
        "/api/v1/reservations",
        json=_booking_body(search.json()[0]["leg_ids"], surname),
        headers={"Idempotency-Key": key or f"reservation-{uuid4()}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _inventory(harness: ApiHarness, leg_id: str) -> tuple[int, int, int]:
    with harness.sessions() as db:
        row = db.scalar(
            select(Inventory).where(
                Inventory.flight_leg_instance_id == leg_id,
                Inventory.cabin == "ECONOMY",
            )
        )
        assert row is not None
        return row.capacity, row.held, row.confirmed


def _assert_error(response: Any, status: int, correlation: str, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    assert body["message"]
    assert body["correlation_id"] == correlation
    assert response.headers["X-Correlation-Id"] == correlation


def test_health_static_openapi_and_stable_errors(api: ApiHarness) -> None:
    assert production_app is app
    health = api.client.get("/api/v1/health", headers={"X-Correlation-Id": "health-cid"})
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.headers["X-Correlation-Id"] == "health-cid"

    for path in ("/", "/styles.css", "/app.js", "/client-logic.js"):
        response = api.client.get(path)
        assert response.status_code == 200
        assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    schema = api.client.get("/openapi.json").json()
    assert {
        "/api/v1/flights/search",
        "/api/v1/reservations",
        "/api/v1/admin/inventory",
        "/api/v1/admin/audit",
    } <= set(schema["paths"])

    invalid = api.client.get(
        "/api/v1/flights/search",
        params={
            "origin": "BOG",
            "destination": "MDE",
            "date": _date_for(api),
            "passengers": 10,
        },
        headers={"X-Correlation-Id": "validation-cid"},
    )
    _assert_error(invalid, 422, "validation-cid", "VALIDATION_ERROR")
    missing = api.client.get("/api/v1/does-not-exist", headers={"X-Correlation-Id": "missing-cid"})
    _assert_error(missing, 404, "missing-cid", "HTTP_ERROR")


def test_unexpected_error_is_sanitized(api: ApiHarness) -> None:
    normal_override = app.dependency_overrides.get(get_db)

    def broken_db() -> Any:
        raise RuntimeError("private database detail")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        response = api.client.get("/api/v1/health", headers={"X-Correlation-Id": "internal-cid"})
    finally:
        if normal_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = normal_override
    _assert_error(response, 500, "internal-cid", "INTERNAL_ERROR")
    assert "private database detail" not in response.text


def test_search_local_time_connections_capacity_and_price_filter(api: ApiHarness) -> None:
    direct = _search(api, "MDE", max_stops=0)
    assert direct.status_code == 200 and direct.json()
    for itinerary in direct.json():
        assert len(itinerary["segments"]) == 1
        assert itinerary["available"] >= 1
        assert itinerary["currency"] == "COP"
        assert itinerary["quote_expires_at"]
        segment = itinerary["segments"][0]
        assert segment["origin"] == "BOG"
        assert segment["departure_at"].endswith("Z") or "+00:00" in segment["departure_at"]
        assert segment["departure_local"] and segment["arrival_local"]
        assert segment["origin_timezone"] == "America/Bogota"

    connection = _search(api, "CLO")
    assert connection.status_code == 200 and connection.json()
    assert len(connection.json()[0]["segments"]) == 2
    assert [item["sequence"] for item in connection.json()[0]["segments"]] == [1, 2]
    assert _search(api, "CLO", max_stops=0).json() == []
    with api.sessions.begin() as db:
        db.execute(
            update(Inventory)
            .where(Inventory.cabin == "ECONOMY")
            .values(held=Inventory.capacity - 6)
        )
    assert _search(api, "MDE", passengers=7).json() == []
    assert _search(api, "MDE", max_price=0).json() == []

    same = api.client.get(
        "/api/v1/flights/search",
        params={
            "origin": "BOG",
            "destination": "BOG",
            "date": _date_for(api),
            "passengers": 1,
        },
        headers={"X-Correlation-Id": "same-cid"},
    )
    _assert_error(same, 422, "same-cid", "VALIDATION_ERROR")


def test_reservation_detail_lookup_and_idempotency(api: ApiHarness) -> None:
    search = _search(api)
    legs = search.json()[0]["leg_ids"]
    body = _booking_body(legs)
    missing_key = api.client.post(
        "/api/v1/reservations",
        json=body,
        headers={"X-Correlation-Id": "key-cid"},
    )
    _assert_error(missing_key, 422, "key-cid", "IDEMPOTENCY_KEY_REQUIRED")

    headers = {"Idempotency-Key": f"replay-{uuid4()}"}
    first = api.client.post("/api/v1/reservations", json=body, headers=headers)
    replay = api.client.post("/api/v1/reservations", json=body, headers=headers)
    assert first.status_code == replay.status_code == 201
    reservation = first.json()
    assert replay.json()["id"] == reservation["id"]
    assert reservation["state"] == "PENDING_PAYMENT"
    assert reservation["passengers"][0]["seat"]
    assert reservation["segments"][0]["departure_local"]
    assert reservation["items"][0]["price"]["total"] == str(
        sum(Decimal(item["price"]["total"]) for item in reservation["items"])
    )
    assert reservation["payments"] == reservation["tickets"] == []

    changed = _booking_body(legs, "Different")
    conflict = api.client.post(
        "/api/v1/reservations",
        json=changed,
        headers={**headers, "X-Correlation-Id": "replay-cid"},
    )
    _assert_error(conflict, 409, "replay-cid", "IDEMPOTENCY_KEY_REUSED")

    lookup = api.client.get(
        f"/api/v1/reservations/{reservation['locator']}", params={"surname": "tester"}
    )
    assert lookup.status_code == 200 and lookup.json()["id"] == reservation["id"]
    wrong = api.client.get(
        f"/api/v1/reservations/{reservation['locator']}",
        params={"surname": "Wrong"},
        headers={"X-Correlation-Id": "surname-cid"},
    )
    _assert_error(wrong, 404, "surname-cid", "NOT_FOUND")
    assert api.client.get(f"/api/v1/reservations/{reservation['id']}/tickets").json() == []


def test_agency_attribution_and_persisted_demo_roles(api: ApiHarness) -> None:
    legs = _search(api).json()[0]["leg_ids"]
    direct_with_agency = _booking_body(legs)
    direct_with_agency.update({"agency_id": "agency-1", "agent_id": "agent-7"})
    response = api.client.post(
        "/api/v1/reservations",
        json=direct_with_agency,
        headers={"Idempotency-Key": f"direct-agency-{uuid4()}"},
    )
    assert response.status_code == 422

    agency_body = _booking_body(legs)
    agency_body.update({"channel": "AGENCY", "agency_id": "agency-1", "agent_id": "agent-7"})
    passenger = api.client.post(
        "/api/v1/reservations",
        json=agency_body,
        headers={"Idempotency-Key": f"passenger-agency-{uuid4()}"},
    )
    assert passenger.status_code == 403
    mismatch = api.client.post(
        "/api/v1/reservations",
        json={**agency_body, "agency_id": "wrong"},
        headers={**AGENT, "Idempotency-Key": f"mismatch-{uuid4()}"},
    )
    assert mismatch.status_code == 403
    accepted = api.client.post(
        "/api/v1/reservations",
        json=agency_body,
        headers={**AGENT, "Idempotency-Key": f"agency-{uuid4()}"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["agency_id"] == "agency-1"
    assert accepted.json()["agent_id"] == "agent-7"

    for path in ("/api/v1/admin/inventory", "/api/v1/flights/no-leg/manifest"):
        assert api.client.get(path).status_code == 403
    forged = api.client.get(
        "/api/v1/admin/inventory",
        headers={"X-Demo-Actor-Id": "demo-passenger", "X-Demo-Role": "ADMIN"},
    )
    assert forged.status_code == 403


def test_approved_payment_manifest_cancel_refund_and_inventory_restore(
    api: ApiHarness,
) -> None:
    reservation = _create(api, destination="CLO", surname="Lifecycle")
    leg_ids = [segment["leg_id"] for segment in reservation["segments"]]
    before = {leg_id: _inventory(api, leg_id) for leg_id in leg_ids}
    assert all(value[1] == 1 for value in before.values())

    operation = f"pay-{uuid4()}"
    payment = api.client.post(
        f"/api/v1/reservations/{reservation['id']}/payments",
        json={"approved": True, "operation_reference": operation},
    )
    replay = api.client.post(
        f"/api/v1/reservations/{reservation['id']}/payments",
        json={"approved": True, "operation_reference": operation},
    )
    assert payment.status_code == replay.status_code == 200
    assert payment.json()["payment_id"] == replay.json()["payment_id"]
    conflict = api.client.post(
        f"/api/v1/reservations/{reservation['id']}/payments",
        json={"approved": False, "operation_reference": operation},
        headers={"X-Correlation-Id": "payment-conflict"},
    )
    _assert_error(conflict, 409, "payment-conflict", "IDEMPOTENCY_KEY_REUSED")

    tickets = api.client.get(f"/api/v1/reservations/{reservation['id']}/tickets")
    assert tickets.status_code == 200
    assert len(tickets.json()[0]["coupons"]) == 2
    assert all(item["seat"] for item in tickets.json()[0]["coupons"])
    manifest = api.client.get(f"/api/v1/flights/{leg_ids[0]}/manifest", headers=AIRPORT)
    assert manifest.status_code == 200 and manifest.json()["passengers"][0]["seat"]

    cancelled = api.client.post(f"/api/v1/reservations/{reservation['id']}/cancel")
    assert cancelled.status_code == 200
    detail = cancelled.json()
    assert detail["state"] == "CANCELLED" and detail["released_at"]
    assert {item["state"] for item in detail["payments"]} == {"APPROVED", "REFUNDED"}
    assert Decimal(detail["refunds"][0]["amount"]) == (
        Decimal(detail["total"]) * Decimal("0.90")
    ).quantize(Decimal("0.01"))
    assert all(item["resource_state"] == "RELEASED" for item in detail["items"])
    assert all(ticket["state"] == "VOID" for ticket in detail["tickets"])
    assert all(
        coupon["state"] == "VOID" for ticket in detail["tickets"] for coupon in ticket["coupons"]
    )
    assert {leg_id: _inventory(api, leg_id) for leg_id in leg_ids} == {
        leg_id: (value[0], 0, 0) for leg_id, value in before.items()
    }
    after_cancel = api.client.get(f"/api/v1/flights/{leg_ids[0]}/manifest", headers=AIRPORT)
    assert after_cancel.status_code == 404


def test_declined_payment_releases_inventory(api: ApiHarness) -> None:
    reservation = _create(api, surname="Declined")
    leg_id = reservation["segments"][0]["leg_id"]
    capacity, held, confirmed = _inventory(api, leg_id)
    assert held == 1 and confirmed == 0
    response = api.client.post(
        f"/api/v1/reservations/{reservation['id']}/payments",
        json={"approved": False, "operation_reference": f"declined-{uuid4()}"},
    )
    assert response.status_code == 200 and response.json()["state"] == "DECLINED"
    lookup = api.client.get(
        f"/api/v1/reservations/{reservation['locator']}", params={"surname": "Declined"}
    ).json()
    assert lookup["state"] == "PAYMENT_FAILED" and lookup["released_at"]
    assert all(item["resource_state"] == "RELEASED" for item in lookup["items"])
    assert _inventory(api, leg_id) == (capacity, 0, 0)


def test_expiration_releases_inventory(api: ApiHarness) -> None:
    reservation = _create(api, surname="Expired")
    leg_id = reservation["segments"][0]["leg_id"]
    capacity, held, _ = _inventory(api, leg_id)
    assert held == 1
    with api.sessions() as db:
        row = db.get(Reservation, reservation["id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    expired = api.client.post("/api/v1/admin/expiration", headers=ADMIN)
    assert expired.status_code == 200 and expired.json()["expired"] == 1
    lookup = api.client.get(
        f"/api/v1/reservations/{reservation['locator']}", params={"surname": "Expired"}
    ).json()
    assert lookup["state"] == "EXPIRED" and lookup["released_at"]
    assert _inventory(api, leg_id) == (capacity, 0, 0)


def test_admin_catalogs_and_runtime_policy_updates(api: ApiHarness) -> None:
    for resource in (
        "inventory",
        "reservations",
        "audit",
        "settings",
        "fare-rules",
        "airports",
        "agencies",
        "agents",
    ):
        response = api.client.get(f"/api/v1/admin/{resource}", headers=ADMIN)
        assert response.status_code == 200 and isinstance(response.json(), list)

    old_quote = _search(api).json()[0]
    tax = api.client.put(
        "/api/v1/admin/fare-rules/ACADEMIC_TAX_RATE",
        json={"value": "0.20"},
        headers=ADMIN,
    )
    assert tax.status_code == 200 and Decimal(tax.json()["value"]) == Decimal("0.20")
    assert Decimal(_search(api).json()[0]["total"]) > Decimal(old_quote["total"])

    setting = api.client.put(
        "/api/v1/admin/settings/hold_minutes",
        json={"value": "7"},
        headers=ADMIN,
    )
    assert setting.status_code == 200 and setting.json()["value"] == "7"
    reservation = _create(api, surname="Policy")
    created = datetime.fromisoformat(reservation["created_at"])
    expires = datetime.fromisoformat(reservation["expires_at"])
    assert abs((expires - created).total_seconds() - 420) < 2

    invalid = api.client.put(
        "/api/v1/admin/settings/hold_minutes",
        json={"value": "0"},
        headers={**ADMIN, "X-Correlation-Id": "policy-cid"},
    )
    _assert_error(invalid, 422, "policy-cid", "VALIDATION_ERROR")
