from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from airline_core.domain.errors import (
    CancellationNotAllowed,
    InvalidState,
    PaymentTooLate,
    ValidationError,
)
from airline_core.domain.itinerary import SegmentTime, validate_itinerary
from airline_core.domain.pricing import advance_multiplier, money, price
from airline_core.domain.state import require_approval, require_cancellation, validate_sale
from airline_core.domain.types import Cabin, ReservationState

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_pricing_bands_rounding_and_agency_commission():
    assert advance_multiplier(NOW + timedelta(days=31), NOW) == Decimal("0.80")
    assert advance_multiplier(NOW + timedelta(days=7), NOW) == Decimal("1.00")
    assert advance_multiplier(NOW + timedelta(days=6), NOW) == Decimal("1.25")
    assert money(Decimal("1.005")) == Decimal("1.01")
    snap = price(
        Decimal("100.005"), Decimal(10), Cabin.BUSINESS, NOW + timedelta(days=31), NOW, True
    )
    assert snap.total == Decimal("169.41") and snap.agency_commission == Decimal("7.20")


def test_itinerary_validation():
    validate_itinerary(
        [
            SegmentTime("BOG", "MDE", NOW, NOW + timedelta(hours=1)),
            SegmentTime(
                "MDE", "CLO", NOW + timedelta(hours=1, minutes=45), NOW + timedelta(hours=3)
            ),
        ]
    )
    with pytest.raises(ValidationError):
        validate_itinerary(
            [
                SegmentTime("BOG", "MDE", NOW, NOW + timedelta(hours=1)),
                SegmentTime("CLO", "CTG", NOW + timedelta(hours=2), NOW + timedelta(hours=3)),
            ]
        )
    with pytest.raises(ValidationError):
        validate_itinerary(
            [
                SegmentTime("BOG", "MDE", NOW, NOW + timedelta(hours=1)),
                SegmentTime(
                    "MDE", "CLO", NOW + timedelta(hours=1, minutes=30), NOW + timedelta(hours=3)
                ),
            ]
        )


def test_cutoffs_and_state_machine():
    validate_sale(NOW + timedelta(minutes=61), NOW)
    with pytest.raises(ValidationError):
        validate_sale(NOW + timedelta(minutes=60), NOW)
    with pytest.raises(ValidationError):
        validate_sale(NOW + timedelta(days=181), NOW)
    with pytest.raises(PaymentTooLate):
        require_approval(ReservationState.PENDING_PAYMENT, NOW, NOW)
    with pytest.raises(InvalidState):
        require_approval(ReservationState.CONFIRMED, NOW + timedelta(hours=1), NOW)
    with pytest.raises(CancellationNotAllowed):
        require_cancellation(ReservationState.CONFIRMED, NOW + timedelta(hours=23), NOW)
