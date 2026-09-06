# Core engine traceability

| Requirement / invariant | Implementation | Automated evidence |
|---|---|---|
| FR-002/003, INV-02 | `domain.itinerary.validate_itinerary`; `BookingService.create` | `test_itinerary_validation`, `test_multi_segment_rollback_and_payment_ticket_once` |
| FR-006 | `domain.state.validate_sale` | `test_cutoffs_and_state_machine` |
| FR-008–010, INV-01–03 | `Inventory` checks, canonical `FOR UPDATE`, partial active-seat index | `test_multi_segment_rollback...`, `test_last_unit_has_one_winner_20_real_postgres` |
| FR-011, FR-021, INV-05 | persisted fingerprint and operation reference unique keys | `test_hold_snapshot_idempotency...`, `test_multi_segment_rollback...` |
| FR-012–014, INV-04/06 | hold deadline, `expire_due`, guarded resource release | `test_decline_expiry_and_cancellation_are_exactly_once`, `test_late_approval_is_rejected` |
| FR-016–020, INV-11 | simulated payment states, confirmation and ticket/coupon uniqueness | `test_multi_segment_rollback_and_payment_ticket_once`, `test_late_approval_is_rejected` |
| FR-022–025, INV-12 | cancellation cutoff, voided tickets/coupons and 90% refund | `test_decline_expiry_and_cancellation_are_exactly_once`, `test_cutoffs_and_state_machine` |
| FR-026/027 | agency attribution check and Decimal commission snapshot | `test_hold_snapshot_idempotency_and_agency_audit`, `test_pricing_bands_rounding_and_agency_commission` |
| FR-032–034, INV-07 | `domain.pricing`, immutable `ReservationItem` snapshot fields | `test_pricing_bands_rounding_and_agency_commission`, `test_hold_snapshot_idempotency...` |
| FR-035 | `AuditEvent` includes actor, time, reason, old/new state, correlation id | `test_hold_snapshot_idempotency_and_agency_audit` |
| FR-007/008/013/018 | `Itinerary`/`ItinerarySegment` plus immutable passenger-segment snapshots | `test_multi_segment_rollback_and_payment_ticket_once`, `test_bootstrap_from_empty_and_idempotent_preserves_commercial_rows` |
| FR-009/028/033 | PostgreSQL named checks, natural unique keys, partial active-seat index and `NUMERIC` | `test_head_schema_contains_all_sqlalchemy_tables_and_critical_constraints`, `test_last_unit_has_one_winner_20_real_postgres` |
| FR-016/021/022/024 | payments, refunds, ticket/coupon states and idempotency-record schema | `test_multi_segment_rollback_and_payment_ticket_once`, `test_decline_expiry_and_cancellation_are_exactly_once` |
| Operational DB | Alembic `0001`–`0003`, advisory migration lock and guarded catalog bootstrap | `test_migration_from_scratch`, `test_each_legacy_revision_upgrades_without_losing_valid_reservation` |

`INV-08` and `INV-09` concern the explicitly out-of-phase OLAP/ETL pipeline. The OLTP model retains approved/refunded payments and distinct `CANCELLED`, `EXPIRED`, and `PAYMENT_FAILED` states so that pipeline can enforce them without inference.
