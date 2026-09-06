"""Runtime commercial and operational policy loaded from PostgreSQL catalogs."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from airline_core.domain.errors import ValidationError
from airline_core.persistence.models import FareRule, OperationalSetting


@dataclass(frozen=True, slots=True)
class Policy:
    hold_minutes: int
    quote_minutes: int
    sales_cutoff_minutes: int
    sales_horizon_days: int
    cancellation_cutoff_hours: int
    refund_percent: Decimal
    advance_gt_30: Decimal
    advance_7_to_30: Decimal
    advance_lt_7: Decimal
    business_multiplier: Decimal
    tax_rate: Decimal
    commission_rate: Decimal


def load_policy(session: Session) -> Policy:
    settings = {x.key: x.value for x in session.scalars(select(OperationalSetting))}
    fares = {
        x.code: x.value for x in session.scalars(select(FareRule).where(FareRule.active.is_(True)))
    }

    def integer(key: str, default: int) -> int:
        try:
            value = int(settings.get(key, str(default)))
        except ValueError:
            raise ValidationError(f"invalid operational setting: {key}")
        if value <= 0:
            raise ValidationError(f"operational setting must be positive: {key}")
        return value

    def decimal(key: str, default: str) -> Decimal:
        try:
            value = Decimal(fares.get(key, Decimal(default)))
        except Exception as exc:
            raise ValidationError(f"invalid fare rule: {key}") from exc
        if value < 0:
            raise ValidationError(f"fare rule must be nonnegative: {key}")
        return value

    try:
        refund = Decimal(settings.get("refund_percent", "90"))
    except Exception as exc:
        raise ValidationError("invalid refund_percent") from exc
    if not 0 <= refund <= 100:
        raise ValidationError("refund_percent must be between 0 and 100")
    tax, commission = decimal("ACADEMIC_TAX_RATE", "0.1"), decimal("AGENCY_COMMISSION_RATE", "0.05")
    if tax > 1 or commission > 1:
        raise ValidationError("tax and commission rates must be <= 1")
    return Policy(
        integer("hold_minutes", 60),
        integer("quote_minutes", 15),
        integer("sales_cutoff_minutes", 60),
        integer("sales_horizon_days", 180),
        integer("cancellation_cutoff_hours", 24),
        refund,
        decimal("ADVANCE_GT_30_DAYS", "0.8"),
        decimal("ADVANCE_7_TO_30_DAYS", "1"),
        decimal("ADVANCE_LT_7_DAYS", "1.25"),
        decimal("BUSINESS_MULTIPLIER", "1.8"),
        tax,
        commission,
    )
