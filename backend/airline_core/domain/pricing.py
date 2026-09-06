from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .types import Cabin

COP = Decimal("0.01")
TAX_RATE = Decimal("0.10")
BUSINESS_MULTIPLIER = Decimal("1.80")
AGENCY_COMMISSION_RATE = Decimal("0.05")


def money(value: Decimal) -> Decimal:
    return value.quantize(COP, rounding=ROUND_HALF_UP)


def advance_multiplier(departure: datetime, now: datetime) -> Decimal:
    days = (departure - now).total_seconds() / 86400
    if days > 30:
        return Decimal("0.80")
    if days >= 7:
        return Decimal("1.00")
    return Decimal("1.25")


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    base_fare: Decimal
    advance_multiplier: Decimal
    cabin_multiplier: Decimal
    airport_fee: Decimal
    tax: Decimal
    total: Decimal
    agency_commission: Decimal


def price(
    base_fare: Decimal,
    airport_fee: Decimal,
    cabin: Cabin,
    departure: datetime,
    now: datetime,
    agency: bool = False,
) -> PriceSnapshot:
    advance = advance_multiplier(departure, now)
    cabin_multiplier = BUSINESS_MULTIPLIER if cabin == Cabin.BUSINESS else Decimal(1)
    fare = money(base_fare * advance * cabin_multiplier)
    fee = money(airport_fee)
    tax = money((fare + fee) * TAX_RATE)
    return PriceSnapshot(
        money(base_fare),
        advance,
        cabin_multiplier,
        fee,
        tax,
        money(fare + fee + tax),
        money(fare * AGENCY_COMMISSION_RATE) if agency else Decimal("0.00"),
    )
