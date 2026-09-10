"""Idempotent operational catalogs and separately opt-in synthetic demo data."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

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

DEMO_CAPACITY = {Cabin.ECONOMY: 150, Cabin.BUSINESS: 12}
SEAT_LETTERS = "ABCDEF"
DEMO_START_DATE = date(2026, 9, 11)
DEMO_END_DATE = date(2026, 9, 20)
BOGOTA = ZoneInfo("America/Bogota")


def _upsert(
    session: Session, table: object, rows: list[dict[str, object]], keys: list[str]
) -> None:
    """Natural keys make repeated runs update definitions without duplicates."""
    stmt = insert(table).values(rows)  # type: ignore[arg-type]
    updates = {key: getattr(stmt.excluded, key) for key in rows[0] if key not in keys}
    session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updates))


def _ensure_demo_seats(session: Session, plane: Aircraft) -> None:
    """Grow the demo aircraft without deleting or relabelling historical seats."""
    existing = {
        seat.label: seat.cabin
        for seat in session.scalars(select(Seat).where(Seat.aircraft_id == plane.id))
    }
    for cabin, target, first_row in (
        (Cabin.BUSINESS, DEMO_CAPACITY[Cabin.BUSINESS], 1),
        (Cabin.ECONOMY, DEMO_CAPACITY[Cabin.ECONOMY], 3),
    ):
        current = sum(value == cabin for value in existing.values())
        row = first_row
        while current < target:
            for letter in SEAT_LETTERS:
                label = f"{row}{letter}"
                if label in existing:
                    continue
                session.add(Seat(aircraft_id=plane.id, label=label, cabin=cabin))
                existing[label] = cabin
                current += 1
                if current == target:
                    break
            row += 1
    session.flush()


def _aircraft(session: Session, code: str, type_id: str) -> Aircraft:
    plane = session.scalar(select(Aircraft).where(Aircraft.code == code))
    if plane is None:
        plane = Aircraft(code=code, aircraft_type_id=type_id, active=True)
        session.add(plane)
        session.flush()
    else:
        plane.aircraft_type_id = type_id
        plane.active = True
    _ensure_demo_seats(session, plane)
    return plane


def _scheduled_flight(
    session: Session,
    number: str,
    route_id: str,
) -> ScheduledFlight:
    flight = session.scalar(select(ScheduledFlight).where(ScheduledFlight.number == number))
    if flight is None:
        flight = ScheduledFlight(number=number, route_id=route_id, active=True)
        session.add(flight)
        session.flush()
    else:
        flight.route_id = route_id
        flight.active = True
    return flight


def _scheduled_leg(
    session: Session,
    flight: ScheduledFlight,
    sequence: int,
    origin: str,
    destination: str,
    base_economy: int,
    base_business: int,
    airport_fee: int,
) -> ScheduledLeg:
    leg = session.scalar(
        select(ScheduledLeg).where(
            ScheduledLeg.scheduled_flight_id == flight.id,
            ScheduledLeg.sequence == sequence,
        )
    )
    if leg is None:
        leg = ScheduledLeg(scheduled_flight_id=flight.id, sequence=sequence)
        session.add(leg)
    leg.origin = origin
    leg.destination = destination
    leg.base_economy = Decimal(base_economy)
    leg.base_business = Decimal(base_business)
    leg.airport_fee = Decimal(airport_fee)
    session.flush()
    return leg


def _flight_instance(
    session: Session,
    flight: ScheduledFlight,
    plane: Aircraft,
    service_date: date,
) -> FlightInstance:
    instance = session.scalar(
        select(FlightInstance).where(
            FlightInstance.scheduled_flight_id == flight.id,
            FlightInstance.service_date == service_date.isoformat(),
        )
    )
    if instance is None:
        instance = FlightInstance(
            scheduled_flight_id=flight.id,
            aircraft_id=plane.id,
            service_date=service_date.isoformat(),
            state=FlightState.SCHEDULED,
        )
        session.add(instance)
        session.flush()
    elif instance.state == FlightState.SCHEDULED:
        instance.aircraft_id = plane.id
    return instance


def _leg_instance(
    session: Session,
    flight_instance: FlightInstance,
    scheduled_leg: ScheduledLeg,
    sequence: int,
    service_date: date,
    departure: time,
    arrival: time,
) -> FlightLegInstance:
    instance = session.scalar(
        select(FlightLegInstance).where(
            FlightLegInstance.flight_instance_id == flight_instance.id,
            FlightLegInstance.sequence == sequence,
        )
    )
    departure_at = datetime.combine(service_date, departure, BOGOTA)
    arrival_at = datetime.combine(service_date, arrival, BOGOTA)
    if instance is None:
        instance = FlightLegInstance(
            flight_instance_id=flight_instance.id,
            scheduled_leg_id=scheduled_leg.id,
            sequence=sequence,
            origin=scheduled_leg.origin,
            destination=scheduled_leg.destination,
            departure_at=departure_at,
            arrival_at=arrival_at,
        )
        session.add(instance)
        session.flush()
    elif flight_instance.state == FlightState.SCHEDULED:
        instance.scheduled_leg_id = scheduled_leg.id
        instance.origin = scheduled_leg.origin
        instance.destination = scheduled_leg.destination
        instance.departure_at = departure_at
        instance.arrival_at = arrival_at
    for cabin, capacity in DEMO_CAPACITY.items():
        inventory = session.scalar(
            select(Inventory).where(
                Inventory.flight_leg_instance_id == instance.id,
                Inventory.cabin == cabin,
            )
        )
        if inventory is None:
            session.add(
                Inventory(
                    flight_leg_instance_id=instance.id,
                    cabin=cabin,
                    capacity=capacity,
                    held=0,
                    confirmed=0,
                )
            )
        else:
            inventory.capacity = capacity
    return instance


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
    """Daily, non-overlapping synthetic rotations through 20 September 2026."""
    seed_parameters(session)
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
            {"code": "MDE-BOG", "origin": "MDE", "destination": "BOG", "active": True},
            {"code": "BOG-CLO", "origin": "BOG", "destination": "CLO", "active": True},
            {"code": "MDE-CLO", "origin": "MDE", "destination": "CLO", "active": True},
            {"code": "CLO-BOG", "origin": "CLO", "destination": "BOG", "active": True},
        ],
        ["code"],
    )
    session.flush()
    legacy_plane = session.scalar(select(Aircraft).where(Aircraft.code == "DEMO-A320"))
    if legacy_plane is not None:
        legacy_plane.code = "DEMO-A320-01"
        session.flush()
    plane_1 = _aircraft(session, "DEMO-A320-01", type_id)
    plane_2 = _aircraft(session, "DEMO-A320-02", type_id)
    routes = {
        route.code: route.id
        for route in session.scalars(
            select(Route).where(Route.code.in_(["BOG-MDE", "MDE-BOG", "BOG-CLO", "CLO-BOG"]))
        )
    }
    schedule = (
        (
            "DE100",
            routes["BOG-MDE"],
            plane_1,
            ((1, "BOG", "MDE", time(7), time(8), 180000, 300000, 22000),),
        ),
        (
            "DE101",
            routes["MDE-BOG"],
            plane_1,
            ((1, "MDE", "BOG", time(9, 15), time(10, 15), 175000, 295000, 22000),),
        ),
        (
            "DE200",
            routes["BOG-CLO"],
            plane_2,
            (
                (1, "BOG", "MDE", time(8), time(9), 170000, 290000, 22000),
                (2, "MDE", "CLO", time(10), time(11), 160000, 280000, 18000),
            ),
        ),
        (
            "DE201",
            routes["CLO-BOG"],
            plane_2,
            ((1, "CLO", "BOG", time(12, 15), time(13, 25), 185000, 305000, 18000),),
        ),
    )
    service_date = DEMO_START_DATE
    while service_date <= DEMO_END_DATE:
        for number, route_id, plane, leg_specs in schedule:
            flight = _scheduled_flight(session, number, route_id)
            flight_instance = _flight_instance(session, flight, plane, service_date)
            for (
                sequence,
                origin,
                destination,
                departure,
                arrival,
                economy,
                business,
                fee,
            ) in leg_specs:
                scheduled_leg = _scheduled_leg(
                    session,
                    flight,
                    sequence,
                    origin,
                    destination,
                    economy,
                    business,
                    fee,
                )
                _leg_instance(
                    session,
                    flight_instance,
                    scheduled_leg,
                    sequence,
                    service_date,
                    departure,
                    arrival,
                )
        service_date += timedelta(days=1)


seed = seed_demo  # backwards-compatible fixture name
