from datetime import datetime, timedelta

from .errors import CancellationNotAllowed, InvalidState, PaymentTooLate, ValidationError
from .types import ReservationState

HOLD = timedelta(minutes=60)
CANCELLATION_CUTOFF = timedelta(hours=24)
SALES_CUTOFF = timedelta(minutes=60)
SALES_HORIZON = timedelta(days=180)


def validate_sale(
    departure: datetime,
    now: datetime,
    cutoff: timedelta = SALES_CUTOFF,
    horizon: timedelta = SALES_HORIZON,
) -> None:
    if departure - now <= cutoff or departure - now > horizon:
        raise ValidationError("Departure outside sales window")


def can_expire(state: ReservationState, expiry: datetime, now: datetime) -> bool:
    return state == ReservationState.PENDING_PAYMENT and now >= expiry


def require_approval(state: ReservationState, expiry: datetime, now: datetime) -> None:
    if now >= expiry:
        raise PaymentTooLate("Hold expired")
    if state != ReservationState.PENDING_PAYMENT:
        raise InvalidState("Reservation is not pending payment")


def require_cancellation(
    state: ReservationState,
    departure: datetime,
    now: datetime,
    cutoff: timedelta = CANCELLATION_CUTOFF,
) -> None:
    if state == ReservationState.PENDING_PAYMENT:
        return
    if state != ReservationState.CONFIRMED or departure - now < cutoff:
        raise CancellationNotAllowed("Cancellation not allowed")
