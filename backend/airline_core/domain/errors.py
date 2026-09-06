class DomainError(Exception):
    """Stable base error; a future HTTP adapter maps ``code`` deterministically."""

    code = "DOMAIN_ERROR"


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class InventoryUnavailable(ConflictError):
    code = "INVENTORY_UNAVAILABLE"


class IdempotencyKeyReused(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


class InvalidState(DomainError):
    code = "INVALID_STATE"


class PaymentTooLate(ConflictError):
    code = "PAYMENT_TOO_LATE"


class CancellationNotAllowed(ConflictError):
    code = "CANCELLATION_NOT_ALLOWED"


class UnsupportedOperation(DomainError):
    code = "UNSUPPORTED_OPERATION"
