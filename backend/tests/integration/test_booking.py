from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from airline_core.application.service import BookingService
from airline_core.domain.errors import IdempotencyKeyReused, InventoryUnavailable, PaymentTooLate
from airline_core.domain.types import PaymentState, ReservationState, TicketState
from airline_core.persistence.models import (
    AuditEvent,
    Coupon,
    Inventory,
    Payment,
    Reservation,
    ReservationItem,
    Ticket,
)

pytestmark = pytest.mark.integration


def test_hold_snapshot_idempotency_and_agency_audit(session, command):
    service = BookingService(session)
    r = service.create(command("same", agency=True))
    session.commit()
    assert (
        r.state == ReservationState.PENDING_PAYMENT
        and r.commission > 0
        and r.expires_at - r.created_at < timedelta(minutes=61)
    )
    assert (
        len(
            session.scalars(
                select(ReservationItem).where(ReservationItem.reservation_id == r.id)
            ).all()
        )
        == 1
    )
    assert service.create(command("same", agency=True)).id == r.id
    with pytest.raises(IdempotencyKeyReused):
        service.create(command("same", two=True, agency=True))
    assert (
        session.scalars(select(AuditEvent).where(AuditEvent.entity_id == r.id))
        .first()
        .correlation_id
        == "test"
    )


def test_idempotency_key_is_reusable_after_24_hours(session, command):
    first = BookingService(session).create(command("expired-key"))
    first.created_at -= timedelta(hours=24, seconds=1)
    session.commit()
    second = BookingService(session).create(command("expired-key"))
    assert second.id != first.id


def test_multi_segment_rollback_and_payment_ticket_once(session, command):
    for inventory in session.scalars(select(Inventory)):
        inventory.capacity = 0
    session.commit()
    with pytest.raises(InventoryUnavailable):
        BookingService(session).create(command("nope", two=True))
    session.rollback()
    assert session.scalar(select(Reservation).where(Reservation.idempotency_key == "nope")) is None
    for inventory in session.scalars(select(Inventory)):
        inventory.capacity = 6 if inventory.cabin == "ECONOMY" else 2
    session.commit()
    r = BookingService(session).create(command("yes"))
    session.commit()
    p = BookingService(session).process_payment(r.id, "op-1", True)
    session.commit()
    assert p.state == PaymentState.APPROVED
    assert len(session.scalars(select(Ticket).where(Ticket.reservation_id == r.id)).all()) == 1
    assert len(session.scalars(select(Coupon)).all()) == 1
    assert BookingService(session).process_payment(r.id, "op-1", True).id == p.id


def test_decline_expiry_and_cancellation_are_exactly_once(session, command):
    r = BookingService(session).create(command("decline"))
    session.commit()
    BookingService(session).process_payment(r.id, "decline-op", False)
    session.commit()
    inv = session.scalar(
        select(Inventory).where(
            Inventory.id
            == session.scalar(
                select(ReservationItem.inventory_id).where(ReservationItem.reservation_id == r.id)
            )
        )
    )
    assert inv.held == 0 and session.get(Reservation, r.id).state == ReservationState.PAYMENT_FAILED
    pending = BookingService(session).create(command("expire"))
    pending.expires_at -= timedelta(minutes=61)
    session.commit()
    assert BookingService(session).expire_due() == 1
    session.commit()
    assert BookingService(session).expire_due() == 0
    confirmed = BookingService(session).create(command("cancel"))
    session.commit()
    BookingService(session).process_payment(confirmed.id, "cancel-op", True)
    session.commit()
    out = BookingService(session).cancel(confirmed.id, "guest")
    session.commit()
    assert out.state == ReservationState.CANCELLED
    assert session.scalar(
        select(Payment).where(
            Payment.reservation_id == out.id, Payment.state == PaymentState.REFUNDED
        )
    ).amount == (out.total * Decimal("0.90")).quantize(Decimal("0.01"))
    assert all(
        x.state == TicketState.VOID
        for x in session.scalars(select(Ticket).where(Ticket.reservation_id == out.id))
    )
    assert BookingService(session).cancel(out.id, "guest").id == out.id


def test_late_approval_is_rejected(session, command):
    r = BookingService(session).create(command("late"))
    r.expires_at -= timedelta(minutes=61)
    session.commit()
    with pytest.raises(PaymentTooLate):
        BookingService(session).process_payment(r.id, "late-op", True)
