"""Versioned HTTP adapter for the transactional airline MVP."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from airline_core.application.policy import load_policy
from airline_core.application.service import BookingService, CreateReservation, PassengerInput
from airline_core.domain.errors import DomainError
from airline_core.domain.pricing import price
from airline_core.domain.types import Cabin, Channel
from airline_core.persistence.database import SessionLocal
from airline_core.persistence.models import (
    Agency,
    Agent,
    Airport,
    AuditEvent,
    Coupon,
    DemoIdentity,
    FareRule,
    FlightInstance,
    FlightLegInstance,
    Inventory,
    OperationalSetting,
    Passenger,
    Payment,
    Refund,
    Reservation,
    ReservationItem,
    ScheduledLeg,
    Seat,
    Ticket,
)

LOGGER = logging.getLogger(__name__)
CURRENCY = "COP"


class PassengerBody(BaseModel):
    given_name: str = Field(min_length=1, max_length=100)
    surname: str = Field(min_length=1, max_length=100)


class ReservationBody(BaseModel):
    leg_ids: list[str] = Field(min_length=1, max_length=2)
    cabin: Cabin
    passengers: list[PassengerBody] = Field(min_length=1, max_length=9)
    channel: Channel = Channel.DIRECT
    agency_id: str | None = None
    agent_id: str | None = None


class PaymentBody(BaseModel):
    approved: bool
    operation_reference: str = Field(min_length=1, max_length=128)


class SegmentOut(BaseModel):
    leg_id: str
    sequence: int
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    departure_local: datetime
    arrival_local: datetime
    origin_timezone: str
    destination_timezone: str
    timezone: str


class FlightOut(BaseModel):
    leg_ids: list[str]
    segments: list[SegmentOut]
    available: int
    total: Decimal
    currency: str = CURRENCY
    quote_expires_at: datetime


class PriceSnapshotOut(BaseModel):
    base_fare: Decimal
    advance_multiplier: Decimal
    cabin_multiplier: Decimal
    airport_fee: Decimal
    tax: Decimal
    total: Decimal
    commission: Decimal


class ReservationItemOut(BaseModel):
    id: str
    passenger_id: str
    flight_leg_instance_id: str
    sequence: int
    seat: str
    resource_state: str
    price: PriceSnapshotOut


class PassengerOut(PassengerBody):
    id: str
    seats: list[str] = Field(default_factory=list)
    seat: str | None = None


class PaymentRecordOut(BaseModel):
    id: str
    operation_reference: str
    state: str
    amount: Decimal
    currency: str
    created_at: datetime


class RefundOut(BaseModel):
    id: str
    payment_id: str
    amount: Decimal
    reason: str
    created_at: datetime


class CouponOut(BaseModel):
    flight_leg_instance_id: str
    state: str
    seat: str


class TicketOut(BaseModel):
    number: str
    state: str
    passenger: PassengerBody
    seat: str | None = None
    coupons: list[CouponOut] = Field(default_factory=list)


class ReservationOut(BaseModel):
    id: str
    locator: str
    state: str
    cabin: str
    channel: str
    actor_id: str
    agency_id: str | None
    agent_id: str | None
    total: Decimal
    commission: Decimal
    currency: str = CURRENCY
    created_at: datetime
    expires_at: datetime
    released_at: datetime | None
    passengers: list[PassengerOut] = Field(default_factory=list)
    segments: list[SegmentOut] = Field(default_factory=list)
    items: list[ReservationItemOut] = Field(default_factory=list)
    payments: list[PaymentRecordOut] = Field(default_factory=list)
    refunds: list[RefundOut] = Field(default_factory=list)
    tickets: list[TicketOut] = Field(default_factory=list)


class PaymentOut(BaseModel):
    payment_id: str
    reservation_id: str
    state: str
    amount: Decimal
    currency: str
    correlation_id: str


class ManifestPassenger(BaseModel):
    ticket_locator: str
    given_name: str
    surname: str
    seat: str


class ManifestOut(BaseModel):
    flight_leg_instance_id: str
    passengers: list[ManifestPassenger]


class HealthOut(BaseModel):
    status: str
    service: str
    version: str


class InventoryAdminOut(BaseModel):
    id: str
    flight_leg_instance_id: str
    cabin: str
    capacity: int
    held: int
    confirmed: int
    available: int


class ReservationAdminOut(BaseModel):
    id: str
    locator: str
    state: str
    cabin: str
    channel: str
    actor_id: str
    agency_id: str | None
    agent_id: str | None
    total: Decimal
    created_at: datetime
    expires_at: datetime
    released_at: datetime | None


class AuditAdminOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    old_state: str | None
    new_state: str
    actor: str
    reason: str
    correlation_id: str
    created_at: datetime


class SettingOut(BaseModel):
    key: str
    value: str
    description: str


class SettingUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=80)


class FareRuleOut(BaseModel):
    code: str
    description: str
    value: Decimal
    active: bool


class FareUpdate(BaseModel):
    value: Decimal = Field(ge=0)
    active: bool | None = None


class AirportOut(BaseModel):
    code: str
    iana_zone: str
    name: str | None


class AgencyOut(BaseModel):
    id: str
    name: str
    active: bool


class AgentOut(BaseModel):
    id: str
    agency_id: str
    display_name: str
    active: bool


class ExpirationOut(BaseModel):
    expired: int


class DemoActor(BaseModel):
    id: str
    role: str
    agency_id: str | None


def get_db(request: Request) -> Session:
    session = getattr(request.state, "database_session", None)
    if not isinstance(session, Session):
        raise TypeError("Database transaction middleware is unavailable")
    return session


DB = Annotated[Session, Depends(get_db)]


def correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if not isinstance(value, str):
        value = request.headers.get("X-Correlation-Id") or str(uuid4())
        request.state.correlation_id = value
    return value


def actor(
    x_demo_actor_id: str | None = Header(default=None, alias="X-Demo-Actor-Id"),
    x_demo_role: str | None = Header(default=None, alias="X-Demo-Role"),
    x_demo_agency_id: str | None = Header(default=None, alias="X-Demo-Agency-Id"),
) -> DemoActor:
    role = (x_demo_role or "PASSENGER").upper().replace("-", "_")
    if role == "AGENT":
        role = "AGENCY_AGENT"
    return DemoActor(
        id=x_demo_actor_id or "demo-passenger",
        role=role,
        agency_id=x_demo_agency_id,
    )


def _verified_identity(db: Session, user: DemoActor) -> DemoIdentity:
    identity = db.scalar(
        select(DemoIdentity).where(
            DemoIdentity.id == user.id,
            DemoIdentity.active.is_(True),
        )
    )
    if (
        identity is None
        or identity.role != user.role
        or (identity.role == "AGENCY_AGENT" and identity.agency_id != user.agency_id)
    ):
        raise HTTPException(
            403,
            {"code": "FORBIDDEN", "message": "Unknown or mismatched demo identity"},
        )
    return identity


def require_role(*roles: str) -> Callable[..., DemoActor]:
    def check(
        user: Annotated[DemoActor, Depends(actor)],
        db: DB,
    ) -> DemoActor:
        _verified_identity(db, user)
        if user.role not in roles:
            raise HTTPException(
                403,
                {"code": "FORBIDDEN", "message": "Insufficient demo role"},
            )
        return user

    return check


ORIGIN_QUERY = Query(min_length=3, max_length=3, alias="origin")
DESTINATION_QUERY = Query(min_length=3, max_length=3, alias="destination")
TRAVEL_DATE_QUERY = Query(alias="date")
PASSENGERS_QUERY = Query(ge=1, le=9)
MAX_STOPS_QUERY = Query(default=1, ge=0, le=1)
MAX_PRICE_QUERY = Query(default=None, ge=0)
IDEMPOTENCY_HEADER = Header(default=None, alias="Idempotency-Key")
CHANNEL_HEADER = Header(default=None, alias="X-Channel")
ACTOR_DEPENDENCY = Depends(actor)
MANIFEST_DEPENDENCY = Depends(require_role("AIRPORT", "ADMIN"))


def _airport_zones(db: Session, codes: set[str]) -> dict[str, str]:
    return {
        code: zone
        for code, zone in db.execute(
            select(Airport.code, Airport.iana_zone).where(Airport.code.in_(codes))
        )
    }


def _segment_out(
    leg: FlightLegInstance,
    sequence: int,
    zones: dict[str, str],
) -> SegmentOut:
    origin_zone = zones[leg.origin]
    destination_zone = zones[leg.destination]
    return SegmentOut(
        leg_id=leg.id,
        sequence=sequence,
        origin=leg.origin,
        destination=leg.destination,
        departure_at=leg.departure_at.astimezone(UTC),
        arrival_at=leg.arrival_at.astimezone(UTC),
        departure_local=leg.departure_at.astimezone(ZoneInfo(origin_zone)),
        arrival_local=leg.arrival_at.astimezone(ZoneInfo(destination_zone)),
        origin_timezone=origin_zone,
        destination_timezone=destination_zone,
        timezone=origin_zone,
    )


def _tickets_out(db: Session, reservation_id: str) -> list[TicketOut]:
    rows = db.execute(
        select(Ticket, Passenger)
        .join(Passenger, Passenger.id == Ticket.passenger_id)
        .where(Ticket.reservation_id == reservation_id)
        .order_by(Ticket.issued_at, Ticket.number)
    ).all()
    result: list[TicketOut] = []
    for ticket, passenger in rows:
        coupons: list[CouponOut] = []
        for coupon in db.scalars(
            select(Coupon)
            .where(Coupon.ticket_id == ticket.id)
            .order_by(Coupon.flight_leg_instance_id)
        ):
            seat = db.scalar(
                select(Seat.label)
                .join(ReservationItem, ReservationItem.seat_id == Seat.id)
                .where(
                    ReservationItem.reservation_id == reservation_id,
                    ReservationItem.passenger_id == ticket.passenger_id,
                    ReservationItem.flight_leg_instance_id == coupon.flight_leg_instance_id,
                )
            )
            coupons.append(
                CouponOut(
                    flight_leg_instance_id=coupon.flight_leg_instance_id,
                    state=str(coupon.state),
                    seat=seat or "",
                )
            )
        result.append(
            TicketOut(
                number=ticket.number,
                state=str(ticket.state),
                passenger=PassengerBody(
                    given_name=passenger.given_name,
                    surname=passenger.surname,
                ),
                seat=coupons[0].seat if coupons else None,
                coupons=coupons,
            )
        )
    return result


def _reservation_out(db: Session, reservation: Reservation) -> ReservationOut:
    passengers = list(
        db.scalars(
            select(Passenger)
            .where(Passenger.reservation_id == reservation.id)
            .order_by(Passenger.id)
        )
    )
    items = list(
        db.scalars(
            select(ReservationItem)
            .where(ReservationItem.reservation_id == reservation.id)
            .order_by(ReservationItem.sequence, ReservationItem.passenger_id)
        )
    )
    leg_ids = list(dict.fromkeys(item.flight_leg_instance_id for item in items))
    legs = {
        leg.id: leg
        for leg in db.scalars(select(FlightLegInstance).where(FlightLegInstance.id.in_(leg_ids)))
    }
    zones = _airport_zones(
        db,
        {code for leg in legs.values() for code in (leg.origin, leg.destination)},
    )
    segments: list[SegmentOut] = []
    seen: set[str] = set()
    for item in items:
        if item.flight_leg_instance_id not in seen:
            seen.add(item.flight_leg_instance_id)
            segments.append(_segment_out(legs[item.flight_leg_instance_id], item.sequence, zones))
    seat_by_item = {
        item.id: db.scalar(select(Seat.label).where(Seat.id == item.seat_id)) or ""
        for item in items
    }
    passenger_out: list[PassengerOut] = []
    for passenger in passengers:
        seats = [seat_by_item[item.id] for item in items if item.passenger_id == passenger.id]
        passenger_out.append(
            PassengerOut(
                id=passenger.id,
                given_name=passenger.given_name,
                surname=passenger.surname,
                seats=seats,
                seat=seats[0] if seats else None,
            )
        )
    item_out = [
        ReservationItemOut(
            id=item.id,
            passenger_id=item.passenger_id,
            flight_leg_instance_id=item.flight_leg_instance_id,
            sequence=item.sequence,
            seat=seat_by_item[item.id],
            resource_state=str(item.resource_state),
            price=PriceSnapshotOut(
                base_fare=item.base_fare,
                advance_multiplier=item.advance_multiplier,
                cabin_multiplier=item.cabin_multiplier,
                airport_fee=item.airport_fee,
                tax=item.tax,
                total=item.total,
                commission=item.commission,
            ),
        )
        for item in items
    ]
    payments = [
        PaymentRecordOut(
            id=payment.id,
            operation_reference=payment.operation_reference,
            state=str(payment.state),
            amount=payment.amount,
            currency=payment.currency,
            created_at=payment.created_at,
        )
        for payment in db.scalars(
            select(Payment)
            .where(Payment.reservation_id == reservation.id)
            .order_by(Payment.created_at, Payment.id)
        )
    ]
    refunds = [
        RefundOut(
            id=refund.id,
            payment_id=refund.payment_id,
            amount=refund.amount,
            reason=refund.reason,
            created_at=refund.created_at,
        )
        for refund in db.scalars(
            select(Refund)
            .where(Refund.reservation_id == reservation.id)
            .order_by(Refund.created_at, Refund.id)
        )
    ]
    return ReservationOut(
        id=reservation.id,
        locator=reservation.locator,
        state=str(reservation.state),
        cabin=str(reservation.cabin),
        channel=str(reservation.channel),
        actor_id=reservation.actor_id,
        agency_id=reservation.agency_id,
        agent_id=reservation.agent_id,
        total=reservation.total,
        commission=reservation.commission,
        created_at=reservation.created_at,
        expires_at=reservation.expires_at,
        released_at=reservation.released_at,
        passengers=passenger_out,
        segments=segments,
        items=item_out,
        payments=payments,
        refunds=refunds,
        tickets=_tickets_out(db, reservation.id),
    )


def _domain_http(exc: DomainError, correlation: str) -> HTTPException:
    statuses = {
        "NOT_FOUND": 404,
        "VALIDATION_ERROR": 422,
        "INVENTORY_UNAVAILABLE": 409,
        "IDEMPOTENCY_KEY_REUSED": 409,
        "PAYMENT_TOO_LATE": 409,
        "CANCELLATION_NOT_ALLOWED": 409,
        "INVALID_STATE": 409,
    }
    return HTTPException(
        status_code=statuses.get(exc.code, 400),
        detail={"code": exc.code, "message": str(exc), "correlation_id": correlation},
    )


router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthOut)
def health(db: DB) -> HealthOut:
    db.execute(select(1))
    return HealthOut(status="ok", service="airline-core", version="v1")


@router.get("/flights/search", response_model=list[FlightOut])
def search_flights(
    db: DB,
    request: Request,
    origin: str = ORIGIN_QUERY,
    destination: str = DESTINATION_QUERY,
    travel_date: date = TRAVEL_DATE_QUERY,
    passengers: int = PASSENGERS_QUERY,
    cabin: Cabin = Cabin.ECONOMY,
    max_stops: int = MAX_STOPS_QUERY,
    max_price: Decimal | None = MAX_PRICE_QUERY,
) -> list[FlightOut]:
    origin, destination = origin.upper(), destination.upper()
    if origin == destination:
        raise HTTPException(
            422,
            {"code": "VALIDATION_ERROR", "message": "Origin and destination must differ"},
        )
    now = datetime.now(UTC)
    policy = load_policy(db)
    BookingService(db).expire_due(correlation=correlation_id(request))
    zones = _airport_zones(db, {origin, destination})
    if origin not in zones or destination not in zones:
        raise HTTPException(
            404,
            {"code": "NOT_FOUND", "message": "Origin or destination airport not found"},
        )
    origin_zone = ZoneInfo(zones[origin])
    local_start = datetime.combine(travel_date, time.min, origin_zone)
    local_end = datetime.combine(travel_date + timedelta(days=1), time.min, origin_zone)
    first_legs = list(
        db.scalars(
            select(FlightLegInstance)
            .join(FlightInstance)
            .where(
                FlightLegInstance.origin == origin,
                FlightLegInstance.departure_at >= local_start.astimezone(UTC),
                FlightLegInstance.departure_at < local_end.astimezone(UTC),
                FlightInstance.state.in_(["SCHEDULED", "DELAYED"]),
            )
            .order_by(FlightLegInstance.departure_at)
        )
    )
    inventories = {
        row.flight_leg_instance_id: row
        for row in db.scalars(select(Inventory).where(Inventory.cabin == cabin))
    }
    candidates: list[list[FlightLegInstance]] = []
    for first in first_legs:
        if first.id not in inventories:
            continue
        if first.destination == destination:
            candidates.append([first])
        if not max_stops or first.destination in {origin, destination}:
            continue
        second_legs = db.scalars(
            select(FlightLegInstance)
            .join(FlightInstance)
            .where(
                FlightLegInstance.origin == first.destination,
                FlightLegInstance.destination == destination,
                FlightLegInstance.departure_at >= first.arrival_at + timedelta(minutes=45),
                FlightLegInstance.departure_at <= first.arrival_at + timedelta(hours=6),
                FlightInstance.state.in_(["SCHEDULED", "DELAYED"]),
            )
            .order_by(FlightLegInstance.departure_at)
        )
        candidates.extend([first, second] for second in second_legs if second.id in inventories)
    scheduled_ids = {leg.scheduled_leg_id for path in candidates for leg in path}
    scheduled = {
        row.id: row
        for row in db.scalars(select(ScheduledLeg).where(ScheduledLeg.id.in_(scheduled_ids)))
    }
    all_codes = {
        code for path in candidates for leg in path for code in (leg.origin, leg.destination)
    }
    zones.update(_airport_zones(db, all_codes))
    results: list[FlightOut] = []
    for path in candidates:
        until_departure = path[0].departure_at - now
        if until_departure <= timedelta(
            minutes=policy.sales_cutoff_minutes
        ) or until_departure > timedelta(days=policy.sales_horizon_days):
            continue
        available = min(
            inventories[leg.id].capacity - inventories[leg.id].held - inventories[leg.id].confirmed
            for leg in path
        )
        if available < passengers:
            continue
        quote_total = (
            sum(
                (
                    price(
                        scheduled[leg.scheduled_leg_id].base_business
                        if cabin is Cabin.BUSINESS
                        else scheduled[leg.scheduled_leg_id].base_economy,
                        scheduled[leg.scheduled_leg_id].airport_fee,
                        cabin,
                        leg.departure_at,
                        now,
                        False,
                        (
                            policy.advance_gt_30,
                            policy.advance_7_to_30,
                            policy.advance_lt_7,
                        ),
                        policy.business_multiplier,
                        policy.tax_rate,
                        policy.commission_rate,
                    ).total
                    for leg in path
                ),
                Decimal("0.00"),
            )
            * passengers
        )
        if max_price is not None and quote_total > max_price:
            continue
        results.append(
            FlightOut(
                leg_ids=[leg.id for leg in path],
                segments=[
                    _segment_out(leg, sequence, zones) for sequence, leg in enumerate(path, 1)
                ],
                available=available,
                total=quote_total,
                quote_expires_at=now + timedelta(minutes=policy.quote_minutes),
            )
        )
    return sorted(results, key=lambda item: (item.segments[0].departure_at, item.total))


@router.post("/reservations", response_model=ReservationOut, status_code=201)
def create_reservation(
    body: ReservationBody,
    db: DB,
    request: Request,
    x_idempotency_key: str | None = IDEMPOTENCY_HEADER,
    x_channel: Channel | None = CHANNEL_HEADER,
    user: DemoActor = ACTOR_DEPENDENCY,
) -> ReservationOut:
    correlation = correlation_id(request)
    if not x_idempotency_key:
        raise HTTPException(
            422,
            {
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "Idempotency-Key header is required",
            },
        )
    identity = _verified_identity(db, user)
    channel = x_channel or body.channel
    if x_channel is not None and x_channel != body.channel:
        raise HTTPException(
            422,
            {"code": "VALIDATION_ERROR", "message": "Channel header and body differ"},
        )
    if channel is Channel.DIRECT and (body.agency_id or body.agent_id):
        raise HTTPException(
            422,
            {
                "code": "VALIDATION_ERROR",
                "message": "Direct reservations cannot include agency attribution",
            },
        )
    if channel is Channel.AGENCY:
        if identity.role != "AGENCY_AGENT":
            raise HTTPException(
                403,
                {"code": "FORBIDDEN", "message": "Agency channel requires an agent"},
            )
        agent_row = db.scalar(select(Agent).where(Agent.id == user.id, Agent.active.is_(True)))
        if (
            agent_row is None
            or not body.agency_id
            or body.agent_id != user.id
            or body.agency_id != user.agency_id
            or agent_row.agency_id != body.agency_id
        ):
            raise HTTPException(
                403,
                {"code": "FORBIDDEN", "message": "Agency attribution does not match identity"},
            )
    try:
        reservation = BookingService(db).create(
            CreateReservation(
                actor_id=user.id,
                channel=channel,
                idempotency_key=x_idempotency_key,
                leg_ids=tuple(body.leg_ids),
                cabin=body.cabin,
                passengers=tuple(
                    PassengerInput(given_name=item.given_name, surname=item.surname)
                    for item in body.passengers
                ),
                agency_id=body.agency_id,
                agent_id=body.agent_id,
                correlation_id=correlation,
            )
        )
        return _reservation_out(db, reservation)
    except DomainError as exc:
        raise _domain_http(exc, correlation) from exc


def _find_reservation(db: Session, locator: str, surname: str) -> Reservation:
    reservation = db.scalar(
        select(Reservation)
        .join(Passenger)
        .where(
            func.upper(Reservation.locator) == locator.upper(),
            func.lower(Passenger.surname) == surname.lower(),
        )
    )
    if reservation is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Reservation not found"})
    return reservation


@router.get("/reservations/{locator}", response_model=ReservationOut)
def get_reservation(
    locator: str,
    db: DB,
    request: Request,
    surname: str = Query(min_length=1),
) -> ReservationOut:
    BookingService(db).expire_due(correlation=correlation_id(request))
    return _reservation_out(db, _find_reservation(db, locator, surname))


@router.post("/reservations/{reservation_id}/payments", response_model=PaymentOut)
def pay(
    reservation_id: str,
    body: PaymentBody,
    db: DB,
    request: Request,
    user: DemoActor = ACTOR_DEPENDENCY,
) -> PaymentOut:
    _verified_identity(db, user)
    correlation = correlation_id(request)
    try:
        payment = BookingService(db).process_payment(
            reservation_id,
            body.operation_reference,
            body.approved,
            user.id,
            correlation,
        )
        return PaymentOut(
            payment_id=payment.id,
            reservation_id=reservation_id,
            state=str(payment.state),
            amount=payment.amount,
            currency=payment.currency,
            correlation_id=correlation,
        )
    except DomainError as exc:
        raise _domain_http(exc, correlation) from exc


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel(
    reservation_id: str,
    db: DB,
    request: Request,
    user: DemoActor = ACTOR_DEPENDENCY,
) -> ReservationOut:
    _verified_identity(db, user)
    correlation = correlation_id(request)
    try:
        reservation = BookingService(db).cancel(reservation_id, user.id, correlation)
        return _reservation_out(db, reservation)
    except DomainError as exc:
        raise _domain_http(exc, correlation) from exc


@router.get("/reservations/{reservation_id}/tickets", response_model=list[TicketOut])
def tickets(reservation_id: str, db: DB) -> list[TicketOut]:
    if db.get(Reservation, reservation_id) is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Reservation not found"})
    return _tickets_out(db, reservation_id)


@router.get("/flights/{leg_id}/manifest", response_model=ManifestOut)
def manifest(
    leg_id: str,
    db: DB,
    _: DemoActor = MANIFEST_DEPENDENCY,
) -> ManifestOut:
    rows = db.execute(
        select(Passenger, Reservation, Seat)
        .join(ReservationItem, ReservationItem.passenger_id == Passenger.id)
        .join(Reservation, Reservation.id == ReservationItem.reservation_id)
        .join(Seat, Seat.id == ReservationItem.seat_id)
        .where(
            ReservationItem.flight_leg_instance_id == leg_id,
            ReservationItem.resource_state == "ACTIVE",
            Reservation.state == "CONFIRMED",
        )
        .order_by(Seat.label)
    ).all()
    if not rows:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Manifest not found"})
    return ManifestOut(
        flight_leg_instance_id=leg_id,
        passengers=[
            ManifestPassenger(
                ticket_locator=reservation.locator,
                given_name=passenger.given_name,
                surname=passenger.surname,
                seat=seat.label,
            )
            for passenger, reservation, seat in rows
        ],
    )


admin = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("ADMIN"))],
)


@admin.get("/inventory", response_model=list[InventoryAdminOut])
def admin_inventory(
    db: DB,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InventoryAdminOut]:
    return [
        InventoryAdminOut(
            id=row.id,
            flight_leg_instance_id=row.flight_leg_instance_id,
            cabin=str(row.cabin),
            capacity=row.capacity,
            held=row.held,
            confirmed=row.confirmed,
            available=row.capacity - row.held - row.confirmed,
        )
        for row in db.scalars(select(Inventory).order_by(Inventory.id).limit(limit))
    ]


@admin.get("/reservations", response_model=list[ReservationAdminOut])
def admin_reservations(
    db: DB,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ReservationAdminOut]:
    return [
        ReservationAdminOut(
            id=row.id,
            locator=row.locator,
            state=str(row.state),
            cabin=str(row.cabin),
            channel=str(row.channel),
            actor_id=row.actor_id,
            agency_id=row.agency_id,
            agent_id=row.agent_id,
            total=row.total,
            created_at=row.created_at,
            expires_at=row.expires_at,
            released_at=row.released_at,
        )
        for row in db.scalars(
            select(Reservation).order_by(Reservation.created_at.desc()).limit(limit)
        )
    ]


@admin.get("/audit", response_model=list[AuditAdminOut])
def admin_audit(
    db: DB,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditAdminOut]:
    return [
        AuditAdminOut(
            id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            old_state=row.old_state,
            new_state=row.new_state,
            actor=row.actor,
            reason=row.reason,
            correlation_id=row.correlation_id,
            created_at=row.created_at,
        )
        for row in db.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        )
    ]


@admin.get("/settings", response_model=list[SettingOut])
def admin_settings(db: DB) -> list[SettingOut]:
    return [
        SettingOut(key=row.key, value=row.value, description=row.description)
        for row in db.scalars(select(OperationalSetting).order_by(OperationalSetting.key))
    ]


@admin.put("/settings/{key}", response_model=SettingOut)
def update_setting(key: str, body: SettingUpdate, db: DB) -> SettingOut:
    row = db.get(OperationalSetting, key)
    if row is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Setting not found"})
    row.value = body.value
    load_policy(db)
    return SettingOut(key=row.key, value=row.value, description=row.description)


@admin.get("/fare-rules", response_model=list[FareRuleOut])
def admin_fare_rules(db: DB) -> list[FareRuleOut]:
    return [
        FareRuleOut(
            code=row.code,
            description=row.description,
            value=row.value,
            active=row.active,
        )
        for row in db.scalars(select(FareRule).order_by(FareRule.code))
    ]


@admin.put("/fare-rules/{code}", response_model=FareRuleOut)
def update_fare(code: str, body: FareUpdate, db: DB) -> FareRuleOut:
    row = db.get(FareRule, code)
    if row is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Fare rule not found"})
    row.value = body.value
    if body.active is not None:
        row.active = body.active
    load_policy(db)
    return FareRuleOut(
        code=row.code,
        description=row.description,
        value=row.value,
        active=row.active,
    )


@admin.get("/airports", response_model=list[AirportOut])
def admin_airports(db: DB) -> list[AirportOut]:
    return [
        AirportOut(code=row.code, iana_zone=row.iana_zone, name=row.name)
        for row in db.scalars(select(Airport).order_by(Airport.code))
    ]


@admin.get("/agencies", response_model=list[AgencyOut])
def admin_agencies(db: DB) -> list[AgencyOut]:
    return [
        AgencyOut(id=row.id, name=row.name, active=row.active)
        for row in db.scalars(select(Agency).order_by(Agency.id))
    ]


@admin.get("/agents", response_model=list[AgentOut])
def admin_agents(db: DB) -> list[AgentOut]:
    return [
        AgentOut(
            id=row.id,
            agency_id=row.agency_id,
            display_name=row.display_name,
            active=row.active,
        )
        for row in db.scalars(select(Agent).order_by(Agent.id))
    ]


@admin.post("/expiration", response_model=ExpirationOut)
def expiration(db: DB, request: Request) -> ExpirationOut:
    return ExpirationOut(expired=BookingService(db).expire_due(correlation=correlation_id(request)))


router.include_router(admin)
app = FastAPI(title="Airline OLTP API", version="1.0.0")


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.middleware("http")
async def correlation_middleware(request: Request, call_next: Any) -> Any:
    request.state.correlation_id = request.headers.get("X-Correlation-Id") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id(request)
    return response


@app.middleware("http")
async def database_transaction_middleware(request: Request, call_next: Any) -> Any:
    session = SessionLocal()
    request.state.database_session = session
    try:
        response = await call_next(request)
        if response.status_code < 400:
            session.commit()
        else:
            session.rollback()
        return response
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.exception_handler(StarletteHTTPException)
async def stable_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    cid = correlation_id(request)
    detail = (
        dict(exc.detail)
        if isinstance(exc.detail, dict)
        else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    )
    detail.setdefault("code", "HTTP_ERROR")
    detail.setdefault("message", "Request failed")
    detail["correlation_id"] = cid
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail},
        headers={"X-Correlation-Id": cid},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    cid = correlation_id(request)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "correlation_id": cid,
            }
        },
        headers={"X-Correlation-Id": cid},
    )


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    cid = correlation_id(request)
    status = 404 if exc.code == "NOT_FOUND" else 422 if exc.code == "VALIDATION_ERROR" else 409
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": str(exc), "correlation_id": cid}},
        headers={"X-Correlation-Id": cid},
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    cid = correlation_id(request)
    LOGGER.exception("Unhandled API error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "correlation_id": cid,
            }
        },
        headers={"X-Correlation-Id": cid},
    )


app.include_router(router)

_frontend = Path(__file__).resolve().parents[2] / "frontend"
if _frontend.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend), name="frontend-assets")


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    return FileResponse(_frontend / "index.html")


@app.get("/styles.css", include_in_schema=False)
def frontend_styles() -> FileResponse:
    return FileResponse(_frontend / "styles.css")


@app.get("/client-logic.js", include_in_schema=False)
def frontend_client_logic() -> FileResponse:
    return FileResponse(_frontend / "client-logic.js")


@app.get("/app.js", include_in_schema=False)
def frontend_app() -> FileResponse:
    return FileResponse(_frontend / "app.js")
