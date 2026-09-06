"""Idempotent operational catalogs and separately opt-in synthetic demo data."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from airline_core.application.service import now_utc
from airline_core.domain.types import Cabin, FlightState

from .models import (
    Agency,
    Agent,
    Aircraft,
    AircraftType,
    Airport,
    CabinCatalog,
    DemoIdentity,
    FareRule,
    FlightInstance,
    FlightLegInstance,
    Inventory,
    OperationalSetting,
    Route,
    ScheduledFlight,
    ScheduledLeg,
    Seat,
)


def _upsert(
    session: Session, table: object, rows: list[dict[str, object]], keys: list[str]
) -> None:
    """Natural keys make repeated runs update definitions without duplicates."""
    stmt = insert(table).values(rows)  # type: ignore[arg-type]
    updates = {key: getattr(stmt.excluded, key) for key in rows[0] if key not in keys}
    session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updates))


def seed_parameters(session: Session) -> None:
    """Required non-PII catalogs. No table is dropped, truncated, or commercially changed."""
    _upsert(
        session,
        CabinCatalog.__table__,
        [
            {"code": "ECONOMY", "display_name": "Economy", "sort_order": 1, "active": True},
            {"code": "BUSINESS", "display_name": "Business", "sort_order": 2, "active": True},
        ],
        ["code"],
    )
    _upsert(
        session,
        Airport.__table__,
        [
            {"code": "BOG", "name": "Bogota El Dorado", "iana_zone": "America/Bogota"},
            {"code": "MDE", "name": "Medellin Jose Maria Cordova", "iana_zone": "America/Bogota"},
            {"code": "CLO", "name": "Cali Alfonso Bonilla Aragon", "iana_zone": "America/Bogota"},
        ],
        ["code"],
    )
    _upsert(
        session,
        FareRule.__table__,
        [
            {
                "code": "ADVANCE_GT_30_DAYS",
                "description": "Advance purchase over 30 days",
                "value": Decimal("0.8000"),
                "active": True,
            },
            {
                "code": "ADVANCE_7_TO_30_DAYS",
                "description": "Advance purchase from 7 through 30 days",
                "value": Decimal("1.0000"),
                "active": True,
            },
            {
                "code": "ADVANCE_LT_7_DAYS",
                "description": "Advance purchase under 7 days",
                "value": Decimal("1.2500"),
                "active": True,
            },
            {
                "code": "BUSINESS_MULTIPLIER",
                "description": "Business cabin multiplier",
                "value": Decimal("1.8000"),
                "active": True,
            },
            {
                "code": "ACADEMIC_TAX_RATE",
                "description": "Academic simulated tax",
                "value": Decimal("0.1000"),
                "active": True,
            },
            {
                "code": "AGENCY_COMMISSION_RATE",
                "description": "Agency commission before tax",
                "value": Decimal("0.0500"),
                "active": True,
            },
        ],
        ["code"],
    )
    _upsert(
        session,
        OperationalSetting.__table__,
        [
            {"key": "hold_minutes", "value": "60", "description": "Pending-payment inventory hold"},
            {"key": "quote_minutes", "value": "15", "description": "Search quote validity"},
            {
                "key": "sales_cutoff_minutes",
                "value": "60",
                "description": "Sales close before departure",
            },
            {
                "key": "sales_horizon_days",
                "value": "180",
                "description": "Maximum advance purchase horizon",
            },
            {
                "key": "cancellation_cutoff_hours",
                "value": "24",
                "description": "Cancellation deadline",
            },
            {
                "key": "refund_percent",
                "value": "90",
                "description": "Simulated cancellation refund",
            },
            {
                "key": "default_airport_fee_cop",
                "value": "22000.00",
                "description": "Configurable default airport fee",
            },
        ],
        ["key"],
    )
    _upsert(
        session,
        DemoIdentity.__table__,
        [
            {"id": "demo-passenger", "role": "PASSENGER", "agency_id": None, "active": True},
            {"id": "demo-admin", "role": "ADMIN", "agency_id": None, "active": True},
            {"id": "demo-airport", "role": "AIRPORT", "agency_id": None, "active": True},
        ],
        ["id"],
    )
    _upsert(
        session,
        AircraftType.__table__,
        [
            {"code": "A320-200", "manufacturer": "Airbus", "model": "A320-200", "active": True},
        ],
        ["code"],
    )


def seed_demo(session: Session) -> None:
    """Synthetic BOG-MDE direct and BOG-MDE-CLO connection; safe to rerun in dev/test."""
    seed_parameters(session)
    if session.scalar(select(Aircraft.id).where(Aircraft.code == "DEMO-A320")):
        return
    type_id = session.scalar(select(AircraftType.id).where(AircraftType.code == "A320-200"))
    assert type_id is not None
    _upsert(
        session,
        Agency.__table__,
        [{"id": "agency-1", "name": "Demo Travel", "active": True}],
        ["id"],
    )
    _upsert(
        session,
        Agent.__table__,
        [{"id": "agent-7", "agency_id": "agency-1", "display_name": "Demo Agent", "active": True}],
        ["id"],
    )
    _upsert(
        session,
        DemoIdentity.__table__,
        [{"id": "agent-7", "role": "AGENCY_AGENT", "agency_id": "agency-1", "active": True}],
        ["id"],
    )
    _upsert(
        session,
        Route.__table__,
        [
            {"code": "BOG-MDE", "origin": "BOG", "destination": "MDE", "active": True},
            {"code": "MDE-CLO", "origin": "MDE", "destination": "CLO", "active": True},
        ],
        ["code"],
    )
    session.flush()
    route_id = session.scalar(select(Route.id).where(Route.code == "BOG-MDE"))
    assert route_id is not None
    plane = Aircraft(code="DEMO-A320", aircraft_type_id=type_id, active=True)
    session.add(plane)
    session.flush()
    session.add_all(
        [Seat(aircraft_id=plane.id, label=f"{i}A", cabin=Cabin.ECONOMY) for i in range(1, 7)]
        + [
            Seat(aircraft_id=plane.id, label="1C", cabin=Cabin.BUSINESS),
            Seat(aircraft_id=plane.id, label="2C", cabin=Cabin.BUSINESS),
        ]
    )
    direct, connection = (
        ScheduledFlight(number="DE100", route_id=route_id, active=True),
        ScheduledFlight(number="DE200", route_id=route_id, active=True),
    )
    session.add_all([direct, connection])
    session.flush()
    spec = [
        (direct, 1, "BOG", "MDE", 180000, 300000, 22000),
        (connection, 1, "BOG", "MDE", 170000, 290000, 22000),
        (connection, 2, "MDE", "CLO", 160000, 280000, 18000),
    ]
    legs = [
        ScheduledLeg(
            scheduled_flight_id=f.id,
            sequence=n,
            origin=o,
            destination=d,
            base_economy=e,
            base_business=b,
            airport_fee=fee,
        )
        for f, n, o, d, e, b, fee in spec
    ]
    session.add_all(legs)
    session.flush()
    start = now_utc().replace(minute=0, second=0, microsecond=0) + timedelta(days=10)
    direct_i = FlightInstance(
        scheduled_flight_id=direct.id,
        aircraft_id=plane.id,
        service_date=str(start.date()),
        state=FlightState.SCHEDULED,
    )
    connection_i = FlightInstance(
        scheduled_flight_id=connection.id,
        aircraft_id=plane.id,
        service_date=str(start.date()),
        state=FlightState.SCHEDULED,
    )
    session.add_all([direct_i, connection_i])
    session.flush()
    instances = [
        FlightLegInstance(
            flight_instance_id=direct_i.id,
            scheduled_leg_id=legs[0].id,
            sequence=1,
            origin="BOG",
            destination="MDE",
            departure_at=start,
            arrival_at=start + timedelta(hours=1),
        ),
        FlightLegInstance(
            flight_instance_id=connection_i.id,
            scheduled_leg_id=legs[1].id,
            sequence=1,
            origin="BOG",
            destination="MDE",
            departure_at=start + timedelta(minutes=30),
            arrival_at=start + timedelta(hours=1, minutes=30),
        ),
        FlightLegInstance(
            flight_instance_id=connection_i.id,
            scheduled_leg_id=legs[2].id,
            sequence=2,
            origin="MDE",
            destination="CLO",
            departure_at=start + timedelta(hours=2, minutes=20),
            arrival_at=start + timedelta(hours=3, minutes=20),
        ),
    ]
    session.add_all(instances)
    session.flush()
    for leg in instances:
        session.add_all(
            [
                Inventory(
                    flight_leg_instance_id=leg.id,
                    cabin=Cabin.ECONOMY,
                    capacity=6,
                    held=0,
                    confirmed=0,
                ),
                Inventory(
                    flight_leg_instance_id=leg.id,
                    cabin=Cabin.BUSINESS,
                    capacity=2,
                    held=0,
                    confirmed=0,
                ),
            ]
        )


seed = seed_demo  # backwards-compatible fixture name
