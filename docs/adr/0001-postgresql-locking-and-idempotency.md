# ADR-0001: PostgreSQL pessimistic inventory locking and operation idempotency

Status: accepted (MVP)

## Context

The source of truth is cabin capacity per dated flight leg. A multi-segment reservation must either retain every requested unit or retain none, even under a last-seat race. Retried clients and payment callbacks must not duplicate commercial effects.

## Decision

Within one PostgreSQL transaction, the booking service obtains `SELECT ... FOR UPDATE` locks on all required `inventories` rows in canonical `(flight_leg_instance_id, cabin)` order, rechecks `capacity - held - confirmed`, assigns seats and creates the reservation. PostgreSQL `CHECK` constraints are a second line of defence.

Reservation idempotency has a 24-hour policy boundary and a database uniqueness scope of `(actor_id, channel, idempotency_key)`. The persisted canonical SHA-256 payload fingerprint distinguishes a safe retry from `IDEMPOTENCY_KEY_REUSED`. Payment idempotency uses the unique synthetic operation reference. Tickets/coupons and refunds have database uniqueness constraints plus state guards.

Expired holds are released by the same application service during new booking and via an explicit `expire_due` operation; a scheduler is optional optimization, never the sole correctness mechanism.

## Consequences

PostgreSQL is mandatory for integration/concurrency proof; SQLite is not used. Locks make the critical path serial under contention, which is an explicit correctness-over-throughput decision for this MVP. The schema records idempotency keys indefinitely for auditability; a retention job may prune keys older than 24 hours only after preserving audit evidence.
