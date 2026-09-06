from datetime import datetime, timedelta

from .errors import CancellationNotAllowed, InvalidState, PaymentTooLate, ValidationError
from .types import ReservationState

HOLD = timedelta(minutes=60)
CANCELLATION_CUTOFF = timedelta(hours=24)
SALES_CUTOFF = timedelta(minutes=60)
SALES_HORIZON = timedelta(days=180)


def validate_sale(departure: datetime, now: datetime) -> None:
    if departure - now <= SALES_CUTOFF or departure - now > SALES_HORIZON:
        raise ValidationError("Departure outside sales window")


def can_expire(state: ReservationState, expiry: datetime, now: datetime) -> bool:
    return state == ReservationState.PENDING_PAYMENT and now >= expiry


def require_approval(state: ReservationState, expiry: datetime, now: datetime) -> None:
    if now >= expiry:
        raise PaymentTooLate("Hold expired")
    if state != ReservationState.PENDING_PAYMENT:
        raise InvalidState("Reservation is not pending payment")


def require_cancellation(state: ReservationState, departure: datetime, now: datetime) -> None:
    if state == ReservationState.PENDING_PAYMENT:
        return
    if state != ReservationState.CONFIRMED or departure - now < CANCELLATION_CUTOFF:
        raise CancellationNotAllowed("Cancellation not allowed")
