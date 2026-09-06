from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC as UTC_TZ
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from airline_core.domain.errors import (
    IdempotencyKeyReused,
    InventoryUnavailable,
    NotFoundError,
    PaymentTooLate,
    ValidationError,
)
from airline_core.domain.itinerary import SegmentTime, validate_itinerary
from airline_core.domain.pricing import price
from airline_core.domain.state import (
    HOLD,
    require_approval,
    require_cancellation,
    validate_sale,
)
from airline_core.domain.types import (
    Cabin,
    Channel,
    PaymentState,
    ReservationState,
    ResourceState,
    TicketState,
)
from airline_core.persistence.models import (
    Aircraft,
    AuditEvent,
    Coupon,
    FlightInstance,
    FlightLegInstance,
    Inventory,
    Itinerary,
    ItinerarySegment,
    Passenger,
    Payment,
    Refund,
    Reservation,
    ReservationItem,
    ScheduledLeg,
    Seat,
    Ticket,
)

UTC = UTC_TZ


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class PassengerInput:
    given_name: str
    surname: str


@dataclass(frozen=True, slots=True)
class CreateReservation:
    actor_id: str
    channel: Channel
    idempotency_key: str
    leg_ids: tuple[str, ...]
    cabin: Cabin
    passengers: tuple[PassengerInput, ...]
    agency_id: str | None = None
    agent_id: str | None = None
    correlation_id: str = "booking"


def fingerprint(command: CreateReservation) -> str:
    value = {
        "legs": command.leg_ids,
        "cabin": command.cabin.value,
        "passengers": [(p.given_name, p.surname) for p in command.passengers],
        "channel": command.channel.value,
        "agency": command.agency_id,
        "agent": command.agent_id,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class BookingService:
    """Synchronous application service. Caller owns a real PostgreSQL Session/transaction."""

    def __init__(self, session: Session, clock: Callable[[], datetime] = now_utc):
        self.s, self.clock = session, clock

    def _audit(
        self,
        entity: str,
        entity_id: str,
        old: str | None,
        new: str,
        actor: str,
        reason: str,
        correlation: str,
    ) -> None:
        self.s.add(
            AuditEvent(
                entity_type=entity,
                entity_id=entity_id,
                old_state=old,
                new_state=new,
                actor=actor,
                reason=reason,
                correlation_id=correlation,
            )
        )

    def _reservation(self, id: str, lock: bool = True) -> Reservation:
        stmt = select(Reservation).where(Reservation.id == id)
        if lock:
            stmt = stmt.with_for_update()
        value = self.s.scalar(stmt)
        if value is None:
            raise NotFoundError("Reservation not found")
        return value

    def _release(self, reservation: Reservation, actor: str, reason: str, correlation: str) -> bool:
        items = list(
            self.s.scalars(
                select(ReservationItem)
                .where(
                    ReservationItem.reservation_id == reservation.id,
                    ReservationItem.resource_state == ResourceState.ACTIVE,
                )
                .with_for_update()
            )
        )
        if not items:
            return False
        inventory_ids = sorted({x.inventory_id for x in items})
        inventories = {
            i.id: i
            for i in self.s.scalars(
                select(Inventory)
                .where(Inventory.id.in_(inventory_ids))
                .order_by(Inventory.flight_leg_instance_id, Inventory.cabin)
                .with_for_update()
            )
        }
        per_inventory: dict[str, int] = {}
        for item in items:
            per_inventory[item.inventory_id] = per_inventory.get(item.inventory_id, 0) + 1
            item.resource_state = ResourceState.RELEASED
        for iid, count in per_inventory.items():
            inv = inventories[iid]
            if reservation.state == ReservationState.CONFIRMED:
                inv.confirmed -= count
            else:
                inv.held -= count
            if inv.held < 0 or inv.confirmed < 0:
                raise RuntimeError("corrupt inventory release")
            self._audit("inventory", inv.id, "OCCUPIED", "RELEASED", actor, reason, correlation)
        reservation.released_at = self.clock()
        return True

    def expire_due(self, actor: str = "system", correlation: str = "expiration") -> int:
        current = self.clock()
        expired = list(
            self.s.scalars(
                select(Reservation)
                .where(
                    Reservation.state == ReservationState.PENDING_PAYMENT,
                    Reservation.expires_at <= current,
                )
                .order_by(Reservation.id)
                .with_for_update()
            )
        )
        for r in expired:
            self._release(r, actor, "hold expired", correlation)
            old = r.state
            r.state = ReservationState.EXPIRED
            self._audit(
                "reservation", r.id, str(old), str(r.state), actor, "hold expired", correlation
            )
        return len(expired)

    def create(self, command: CreateReservation) -> Reservation:
        if not command.idempotency_key:
            raise ValidationError("idempotency key required")
        if not 1 <= len(command.passengers) <= 9:
            raise ValidationError("1 to 9 passengers required")
        if command.channel is Channel.AGENCY and not (command.agency_id and command.agent_id):
            raise ValidationError("agency attribution required")
        digest = fingerprint(command)
        # PostgreSQL transaction advisory lock serializes an otherwise absent idempotency row.
        # The inventory locks below still remain the authority for capacity.
        lock_key = f"{command.actor_id}|{command.channel}|{command.idempotency_key}"
        self.s.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))
        prior = self.s.scalar(
            select(Reservation)
            .where(
                Reservation.actor_id == command.actor_id,
                Reservation.channel == command.channel,
                Reservation.idempotency_key == command.idempotency_key,
                Reservation.created_at >= self.clock() - timedelta(hours=24),
            )
            .order_by(Reservation.created_at.desc())
        )
        if prior:
            if prior.payload_hash != digest:
                raise IdempotencyKeyReused("Idempotency key has another payload")
            return prior
        self.expire_due(correlation=command.correlation_id)
        legs = list(
            self.s.scalars(
                select(FlightLegInstance).where(FlightLegInstance.id.in_(command.leg_ids))
            )
        )
        by_id = {l.id: l for l in legs}
        if len(legs) != len(command.leg_ids) or len(set(command.leg_ids)) != len(command.leg_ids):
            raise ValidationError("Unknown or duplicated leg")
        ordered = [by_id[x] for x in command.leg_ids]
        validate_itinerary(
            [SegmentTime(x.origin, x.destination, x.departure_at, x.arrival_at) for x in ordered]
        )
        validate_sale(ordered[0].departure_at, self.clock())
        # Canonical lock order is independent of customer itinerary order.
        inventories = list(
            self.s.scalars(
                select(Inventory)
                .where(
                    Inventory.flight_leg_instance_id.in_(command.leg_ids),
                    Inventory.cabin == command.cabin,
                )
                .order_by(Inventory.flight_leg_instance_id, Inventory.cabin)
                .with_for_update()
            )
        )
        if len(inventories) != len(ordered) or any(
            x.capacity - x.held - x.confirmed < len(command.passengers) for x in inventories
        ):
            raise InventoryUnavailable("Insufficient cabin inventory")
        inv_for_leg = {x.flight_leg_instance_id: x for x in inventories}
        scheduled = {
            x.id: x
            for x in self.s.scalars(
                select(ScheduledLeg).where(
                    ScheduledLeg.id.in_([x.scheduled_leg_id for x in ordered])
                )
            )
        }
        aircraft_by_leg = {
            x.id: self.s.scalar(
                select(Aircraft.id)
                .join(FlightInstance, Aircraft.id == FlightInstance.aircraft_id)
                .join(FlightLegInstance, FlightLegInstance.flight_instance_id == FlightInstance.id)
                .where(FlightLegInstance.id == x.id)
            )
            for x in ordered
        }
        r = Reservation(
            locator=secrets.token_hex(3).upper(),
            state=ReservationState.PENDING_PAYMENT,
            cabin=command.cabin,
            channel=command.channel,
            actor_id=command.actor_id,
            agency_id=command.agency_id,
            agent_id=command.agent_id,
            expires_at=self.clock() + HOLD,
            idempotency_key=command.idempotency_key,
            idempotency_scope=f"{command.idempotency_key}:{secrets.token_hex(12)}",
            payload_hash=digest,
            total=Decimal(0),
            commission=Decimal(0),
        )
        self.s.add(r)
        self.s.flush()
        itinerary = Itinerary(reservation_id=r.id)
        self.s.add(itinerary)
        self.s.flush()
        self.s.add_all(
            [
                ItinerarySegment(
                    itinerary_id=itinerary.id, flight_leg_instance_id=leg.id, sequence=sequence
                )
                for sequence, leg in enumerate(ordered, 1)
            ]
        )
        passengers = [
            Passenger(reservation_id=r.id, given_name=p.given_name, surname=p.surname)
            for p in command.passengers
        ]
        self.s.add_all(passengers)
        self.s.flush()
        total = Decimal(0)
        commission = Decimal(0)
        for seq, leg in enumerate(ordered, 1):
            seats = list(
                self.s.scalars(
                    select(Seat)
                    .where(
                        Seat.aircraft_id == aircraft_by_leg[leg.id],
                        Seat.cabin == command.cabin,
                        ~Seat.id.in_(
                            select(ReservationItem.seat_id).where(
                                ReservationItem.flight_leg_instance_id == leg.id,
                                ReservationItem.resource_state == ResourceState.ACTIVE,
                            )
                        ),
                    )
                    .order_by(Seat.label)
                    .with_for_update()
                )
            )
            if len(seats) < len(passengers):
                raise InventoryUnavailable("Insufficient physical seats")
            sl = scheduled[leg.scheduled_leg_id]
            base = sl.base_business if command.cabin is Cabin.BUSINESS else sl.base_economy
            snap = price(
                base,
                sl.airport_fee,
                command.cabin,
                leg.departure_at,
                self.clock(),
                command.channel == Channel.AGENCY,
            )
            for passenger, seat in zip(passengers, seats):
                self.s.add(
                    ReservationItem(
                        reservation_id=r.id,
                        passenger_id=passenger.id,
                        flight_leg_instance_id=leg.id,
                        inventory_id=inv_for_leg[leg.id].id,
                        seat_id=seat.id,
                        sequence=seq,
                        base_fare=snap.base_fare,
                        advance_multiplier=snap.advance_multiplier,
                        cabin_multiplier=snap.cabin_multiplier,
                        airport_fee=snap.airport_fee,
                        tax=snap.tax,
                        total=snap.total,
                        commission=snap.agency_commission,
                    )
                )
                total += snap.total
                commission += snap.agency_commission
            inv_for_leg[leg.id].held += len(passengers)
            self._audit(
                "inventory",
                inv_for_leg[leg.id].id,
                "AVAILABLE",
                "HELD",
                command.actor_id,
                "reservation hold",
                command.correlation_id,
            )
        r.total, r.commission = total, commission
        self._audit(
            "reservation",
            r.id,
            None,
            str(r.state),
            command.actor_id,
            "reservation created",
            command.correlation_id,
        )
        try:
            self.s.flush()
        except IntegrityError as error:
            raise InventoryUnavailable("Concurrent seat assignment conflict") from error
        return r

    def process_payment(
        self,
        reservation_id: str,
        operation_reference: str,
        approved: bool,
        actor: str = "payment",
        correlation: str = "payment",
    ) -> Payment:
        existing = self.s.scalar(
            select(Payment).where(Payment.operation_reference == operation_reference)
        )
        if existing:
            return existing
        r = self._reservation(reservation_id)
        if approved:
            try:
                require_approval(r.state, r.expires_at, self.clock())
            except PaymentTooLate:
                self.expire_due(correlation=correlation)
                raise
            p = Payment(
                reservation_id=r.id,
                operation_reference=operation_reference,
                state=PaymentState.APPROVED,
                amount=r.total,
            )
            self.s.add(p)
            items = list(
                self.s.scalars(
                    select(ReservationItem)
                    .where(
                        ReservationItem.reservation_id == r.id,
                        ReservationItem.resource_state == ResourceState.ACTIVE,
                    )
                    .with_for_update()
                )
            )
            ids = sorted({x.inventory_id for x in items})
            invs = {
                x.id: x
                for x in self.s.scalars(
                    select(Inventory)
                    .where(Inventory.id.in_(ids))
                    .order_by(Inventory.flight_leg_instance_id, Inventory.cabin)
                    .with_for_update()
                )
            }
            for item in items:
                invs[item.inventory_id].held -= 1
                invs[item.inventory_id].confirmed += 1
            old = r.state
            r.state = ReservationState.CONFIRMED
            self._audit(
                "reservation", r.id, str(old), str(r.state), actor, "payment approved", correlation
            )
            self._audit(
                "payment",
                p.id,
                PaymentState.PENDING.value,
                str(p.state),
                actor,
                "approved",
                correlation,
            )
            passengers = list(
                self.s.scalars(select(Passenger).where(Passenger.reservation_id == r.id))
            )
            for passenger in passengers:
                ticket = Ticket(
                    reservation_id=r.id,
                    passenger_id=passenger.id,
                    number="T" + secrets.token_hex(8).upper(),
                    state=TicketState.ISSUED,
                )
                self.s.add(ticket)
                self.s.flush()
                for item in (x for x in items if x.passenger_id == passenger.id):
                    self.s.add(
                        Coupon(
                            ticket_id=ticket.id,
                            flight_leg_instance_id=item.flight_leg_instance_id,
                            state=TicketState.ISSUED,
                        )
                    )
            return p
        p = Payment(
            reservation_id=r.id,
            operation_reference=operation_reference,
            state=PaymentState.DECLINED,
            amount=r.total,
        )
        self.s.add(p)
        if r.state == ReservationState.PENDING_PAYMENT:
            self._release(r, actor, "payment declined", correlation)
            old = r.state
            r.state = ReservationState.PAYMENT_FAILED
            self._audit(
                "reservation", r.id, str(old), str(r.state), actor, "payment declined", correlation
            )
        self._audit(
            "payment",
            p.id,
            PaymentState.PENDING.value,
            str(p.state),
            actor,
            "declined",
            correlation,
        )
        return p

    def cancel(self, reservation_id: str, actor: str, correlation: str = "cancel") -> Reservation:
        r = self._reservation(reservation_id)
        if r.state == ReservationState.CANCELLED:
            return r
        first = self.s.scalar(
            select(FlightLegInstance.departure_at)
            .join(ReservationItem, ReservationItem.flight_leg_instance_id == FlightLegInstance.id)
            .where(ReservationItem.reservation_id == r.id)
            .order_by(ReservationItem.sequence)
            .limit(1)
        )
        if first is None:
            raise NotFoundError("Reservation itinerary missing")
        require_cancellation(r.state, first, self.clock())
        old = r.state
        if r.state == ReservationState.CONFIRMED:
            self._release(r, actor, "cancelled", correlation)
            for ticket in self.s.scalars(
                select(Ticket).where(Ticket.reservation_id == r.id).with_for_update()
            ):
                ticket.state = TicketState.VOID
                for coupon in self.s.scalars(select(Coupon).where(Coupon.ticket_id == ticket.id)):
                    coupon.state = TicketState.VOID
            refund_payment = Payment(
                reservation_id=r.id,
                operation_reference=f"refund:{r.id}",
                state=PaymentState.REFUNDED,
                amount=(r.total * Decimal("0.90")).quantize(Decimal("0.01")),
            )
            self.s.add(refund_payment)
            self.s.flush()
            self.s.add(
                Refund(
                    payment_id=refund_payment.id,
                    reservation_id=r.id,
                    amount=refund_payment.amount,
                    reason="cancelled reservation",
                )
            )
        else:
            self._release(r, actor, "cancelled pending hold", correlation)
        r.state = ReservationState.CANCELLED
        self._audit("reservation", r.id, str(old), str(r.state), actor, "cancelled", correlation)
        return r
