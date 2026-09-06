from enum import StrEnum


class Cabin(StrEnum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"


class ReservationState(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ResourceState(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"


class PaymentState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"


class TicketState(StrEnum):
    ISSUED = "ISSUED"
    VOID = "VOID"


class Channel(StrEnum):
    DIRECT = "DIRECT"
    AGENCY = "AGENCY"


class FlightState(StrEnum):
    SCHEDULED = "SCHEDULED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
