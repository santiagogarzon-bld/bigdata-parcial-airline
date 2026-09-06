from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from airline_core.domain.types import (
    Cabin,
    Channel,
    FlightState,
    PaymentState,
    ReservationState,
    ResourceState,
    TicketState,
)


class Base(DeclarativeBase):
    pass


def uid() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))


def utcnow() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Airport(Base):
    __tablename__ = "airports"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    iana_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (CheckConstraint("code ~ '^[A-Z]{3}$'", name="ck_airport_iata"),)


class CabinCatalog(Base):
    """Small operational catalog; cabin values remain CHECK-constrained strings for portability."""

    __tablename__ = "cabins"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (CheckConstraint("sort_order > 0", name="ck_cabin_sort_order"),)


class AircraftType(Base):
    __tablename__ = "aircraft_types"
    id: Mapped[str] = uid()
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    manufacturer: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Aircraft(Base):
    __tablename__ = "aircraft"
    id: Mapped[str] = uid()
    code: Mapped[str] = mapped_column(String(20), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    aircraft_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("aircraft_types.id", ondelete="RESTRICT", onupdate="CASCADE")
    )


class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[str] = uid()
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(8), nullable=False)
    cabin: Mapped[Cabin] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        UniqueConstraint("aircraft_id", "label"),
        CheckConstraint("cabin IN ('ECONOMY', 'BUSINESS')", name="ck_seat_cabin"),
    )


class ScheduledFlight(Base):
    __tablename__ = "scheduled_flights"
    id: Mapped[str] = uid()
    number: Mapped[str] = mapped_column(String(10), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    route_id: Mapped[str | None] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT", onupdate="CASCADE")
    )


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = uid()
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    origin: Mapped[str] = mapped_column(
        ForeignKey("airports.code", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    destination: Mapped[str] = mapped_column(
        ForeignKey("airports.code", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (CheckConstraint("origin <> destination", name="ck_route_distinct_airports"),)


class ScheduledLeg(Base):
    __tablename__ = "scheduled_legs"
    id: Mapped[str] = uid()
    scheduled_flight_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_flights.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.code"), nullable=False)
    destination: Mapped[str] = mapped_column(ForeignKey("airports.code"), nullable=False)
    base_economy: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    base_business: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    airport_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    __table_args__ = (
        UniqueConstraint("scheduled_flight_id", "sequence"),
        CheckConstraint("sequence > 0"),
        CheckConstraint("origin <> destination"),
        CheckConstraint("base_economy >= 0 AND base_business >= 0 AND airport_fee >= 0"),
    )


class FlightInstance(Base):
    __tablename__ = "flight_instances"
    id: Mapped[str] = uid()
    scheduled_flight_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_flights.id"), nullable=False
    )
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id"), nullable=False)
    service_date: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[FlightState] = mapped_column(
        String(16), nullable=False, default=FlightState.SCHEDULED
    )
    __table_args__ = (
        UniqueConstraint("scheduled_flight_id", "service_date"),
        CheckConstraint(
            "state IN ('SCHEDULED', 'DELAYED', 'CANCELLED', 'COMPLETED')",
            name="ck_flight_instance_state",
        ),
    )


class FlightLegInstance(Base):
    __tablename__ = "flight_leg_instances"
    id: Mapped[str] = uid()
    flight_instance_id: Mapped[str] = mapped_column(
        ForeignKey("flight_instances.id"), nullable=False
    )
    scheduled_leg_id: Mapped[str] = mapped_column(ForeignKey("scheduled_legs.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.code"), nullable=False)
    destination: Mapped[str] = mapped_column(ForeignKey("airports.code"), nullable=False)
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("flight_instance_id", "sequence"),
        CheckConstraint("arrival_at > departure_at"),
    )


class Inventory(Base):
    __tablename__ = "inventories"
    id: Mapped[str] = uid()
    flight_leg_instance_id: Mapped[str] = mapped_column(
        ForeignKey("flight_leg_instances.id"), nullable=False
    )
    cabin: Mapped[Cabin] = mapped_column(String(16), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    held: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("flight_leg_instance_id", "cabin"),
        CheckConstraint(
            "capacity >= 0 AND held >= 0 AND confirmed >= 0 AND capacity >= held + confirmed",
            name="ck_inventory_nonnegative",
        ),
        CheckConstraint("cabin IN ('ECONOMY', 'BUSINESS')", name="ck_inventory_cabin"),
    )


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = uid()
    locator: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    state: Mapped[ReservationState] = mapped_column(String(24), nullable=False)
    cabin: Mapped[Cabin] = mapped_column(String(16), nullable=False)
    channel: Mapped[Channel] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agency_id: Mapped[str | None] = mapped_column(
        ForeignKey("agencies.id", ondelete="RESTRICT", onupdate="CASCADE")
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT", onupdate="CASCADE")
    )
    created_at: Mapped[datetime] = utcnow()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # A fresh opaque scope is used after the 24-hour business window; the raw key remains auditable.
    idempotency_scope: Mapped[str] = mapped_column(String(196), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "channel", "idempotency_scope", name="uq_reservation_idempotency"
        ),
        CheckConstraint(
            "(channel <> 'AGENCY') OR (agency_id IS NOT NULL AND agent_id IS NOT NULL)",
            name="ck_agency_attribution",
        ),
        CheckConstraint("total >= 0 AND commission >= 0", name="ck_reservation_money_nonnegative"),
        CheckConstraint(
            "state IN ('PENDING_PAYMENT', 'CONFIRMED', 'PAYMENT_FAILED', 'EXPIRED', 'CANCELLED')",
            name="ck_reservation_state",
        ),
        CheckConstraint("cabin IN ('ECONOMY', 'BUSINESS')", name="ck_reservation_cabin"),
        CheckConstraint("channel IN ('DIRECT', 'AGENCY')", name="ck_reservation_channel"),
    )


class Passenger(Base):
    __tablename__ = "passengers"
    id: Mapped[str] = uid()
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    surname: Mapped[str] = mapped_column(String(100), nullable=False)


class Itinerary(Base):
    __tablename__ = "itineraries"
    id: Mapped[str] = uid()
    reservation_id: Mapped[str] = mapped_column(
        ForeignKey("reservations.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = utcnow()


class ItinerarySegment(Base):
    __tablename__ = "itinerary_segments"
    id: Mapped[str] = uid()
    itinerary_id: Mapped[str] = mapped_column(
        ForeignKey("itineraries.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    flight_leg_instance_id: Mapped[str] = mapped_column(
        ForeignKey("flight_leg_instances.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("itinerary_id", "sequence"),
        UniqueConstraint("itinerary_id", "flight_leg_instance_id"),
        CheckConstraint("sequence > 0", name="ck_itinerary_segment_sequence"),
    )


class ReservationItem(Base):
    __tablename__ = "reservation_items"
    id: Mapped[str] = uid()
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    passenger_id: Mapped[str] = mapped_column(ForeignKey("passengers.id"), nullable=False)
    flight_leg_instance_id: Mapped[str] = mapped_column(
        ForeignKey("flight_leg_instances.id"), nullable=False
    )
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id"), nullable=False)
    seat_id: Mapped[str] = mapped_column(ForeignKey("seats.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_state: Mapped[ResourceState] = mapped_column(
        String(16), nullable=False, default=ResourceState.ACTIVE
    )
    base_fare: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    advance_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cabin_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    airport_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    __table_args__ = (
        UniqueConstraint("passenger_id", "flight_leg_instance_id"),
        Index(
            "uq_active_seat_assignment",
            "flight_leg_instance_id",
            "seat_id",
            unique=True,
            postgresql_where=(resource_state == ResourceState.ACTIVE),
        ),
        Index("ix_reservation_items_reservation_sequence", "reservation_id", "sequence"),
        CheckConstraint("sequence > 0", name="ck_reservation_item_sequence"),
        CheckConstraint(
            "base_fare >= 0 AND airport_fee >= 0 AND tax >= 0 AND total >= 0 AND commission >= 0",
            name="ck_reservation_item_money_nonnegative",
        ),
        CheckConstraint(
            "resource_state IN ('ACTIVE', 'RELEASED')", name="ck_reservation_item_state"
        ),
    )


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = uid()
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    operation_reference: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    state: Mapped[PaymentState] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="COP")
    created_at: Mapped[datetime] = utcnow()
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_amount_nonnegative"),
        CheckConstraint(
            "state IN ('PENDING', 'APPROVED', 'DECLINED', 'REFUNDED')", name="ck_payment_state"
        ),
        CheckConstraint("currency = 'COP'", name="ck_payment_currency"),
        Index("ix_payment_reservation_created", "reservation_id", "created_at"),
    )


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = uid()
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        unique=True,
    )
    reservation_id: Mapped[str] = mapped_column(
        ForeignKey("reservations.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = utcnow()
    __table_args__ = (CheckConstraint("amount >= 0", name="ck_refund_amount_nonnegative"),)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = uid()
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    passenger_id: Mapped[str] = mapped_column(ForeignKey("passengers.id"), nullable=False)
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    state: Mapped[TicketState] = mapped_column(String(16), nullable=False)
    issued_at: Mapped[datetime] = utcnow()
    __table_args__ = (
        UniqueConstraint("reservation_id", "passenger_id"),
        CheckConstraint("state IN ('ISSUED', 'VOID')", name="ck_ticket_state"),
    )


class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[str] = uid()
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    flight_leg_instance_id: Mapped[str] = mapped_column(
        ForeignKey("flight_leg_instances.id"), nullable=False
    )
    state: Mapped[TicketState] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        UniqueConstraint("ticket_id", "flight_leg_instance_id"),
        CheckConstraint("state IN ('ISSUED', 'VOID')", name="ck_coupon_state"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = uid()
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    old_state: Mapped[str | None] = mapped_column(String(32))
    new_state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = utcnow()
    data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_audit_events_entity_created", "entity_type", "entity_id", "created_at"),
    )


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    agency_id: Mapped[str] = mapped_column(
        ForeignKey("agencies.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class DemoIdentity(Base):
    __tablename__ = "demo_identities"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agencies.id", ondelete="RESTRICT"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (
        CheckConstraint(
            "role IN ('PASSENGER','AGENCY_AGENT','ADMIN','AIRPORT')", name="ck_demo_identity_role"
        ),
    )


class FareRule(Base):
    __tablename__ = "fare_rules"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (CheckConstraint("value >= 0", name="ck_fare_rule_value_nonnegative"),)


class OperationalSetting(Base):
    __tablename__ = "operational_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[str] = uid()
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = utcnow()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("scope", "actor_id", "idempotency_key", name="uq_idempotency_record"),
    )
