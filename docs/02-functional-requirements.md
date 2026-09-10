# Functional Requirements

Status: **proposed baseline pending team confirmation**

This specification translates the business definitions in [01-definicion-del-proyecto.md](./01-definicion-del-proyecto.md) into testable behavior. Requirements use MoSCoW priorities: Must, Should, Could, and Won't for the MVP.

## Scope conventions

- A reservation holds inventory but is not itself proof of purchase.
- A purchase occurs only when the simulated payment is approved.
- Approval issues one immutable ticket per passenger, with one coupon per itinerary segment.
- “Update” and “delete” operations on reservations or tickets are replaced by explicit, auditable state transitions.
- A recurring commercial flight may contain multiple ordered legs under the same flight number.
- The MVP supports one-way passenger itineraries with one or two booked segments.
- All personal and payment data used in demonstrations will be synthetic.

## Passenger and flight-search requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-001 | The system shall search one-way itineraries using origin, destination, local departure date, passenger count, and cabin as mandatory criteria. | Passenger, agency agent | Must | A valid request returns only itineraries matching all mandatory criteria; equal origin/destination or 0/10+ passengers returns a validation error. | Q-028, Q-033 |
| FR-002 | The search shall return direct itineraries and itineraries with at most one connection. | Passenger, agency agent | Must | No result contains more than two ordered segments. | Q-031–Q-033 |
| FR-003 | A connecting itinerary shall use contiguous flight-leg instances at the same airport with a layover between 45 minutes and 6 hours. | System | Must | Results violating airport continuity or either time limit are excluded; ordered legs under one commercial flight remain distinguishable. | Q-018, Q-029, Q-031 |
| FR-004 | Search results shall expose segment schedules, local time zones, cabin, minimum itinerary availability, total quoted price, and quote expiration. | Passenger, agency agent | Must | Every returned itinerary contains those fields and a quote valid for 15 minutes. | Q-029, Q-033, Q-045 |
| FR-005 | Search availability shall exclude expired holds and inventory assigned to active or confirmed reservations. | System | Must | An expired hold never prevents another valid reservation, even before asynchronous cleanup runs. | Q-019, INV-04 |
| FR-006 | The system shall reject a new reservation outside the 180-day sales horizon or within 60 minutes of first-segment departure. | Passenger, agency agent | Must | Boundary tests demonstrate acceptance/rejection immediately before and after both limits. | Q-028 |

## Reservation and inventory requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-007 | The system shall create one reservation containing one itinerary, 1–9 passengers, and all ordered segments selected from a valid quote. | Passenger, agency agent | Must | The persisted reservation preserves passenger, segment, cabin, and price-snapshot relationships. | Q-018, Q-033, Q-035 |
| FR-008 | Reservation creation shall atomically retain capacity for every passenger on every segment or retain nothing. | System | Must | If any segment lacks capacity, the operation rolls back without a reservation, seat assignment, or inventory decrement. | Q-018, Q-020, INV-02 |
| FR-009 | The system shall prevent cabin availability from becoming negative and prevent duplicate physical-seat assignment for the same flight-leg instance. | System | Must | Constraints and a concurrent integration test demonstrate both invariants while allowing a seat to be reused on a later, non-overlapping leg. | Q-020, INV-01, INV-03 |
| FR-010 | The system shall serialize competing reservations by locking required flight-leg inventory rows in canonical order and rechecking availability inside the transaction. | System | Must | With one remaining unit on any requested leg and simultaneous requests, exactly one reservation succeeds and inventory remains zero. | Q-021 |
| FR-011 | Creating a reservation shall require an idempotency key scoped to actor/channel for 24 hours. | Passenger, agency agent | Must | Same key and payload returns the original result; same key with a different payload returns `409 IDEMPOTENCY_KEY_REUSED`. | Q-044 |
| FR-012 | A new reservation shall enter `PENDING_PAYMENT` and hold all assigned capacity and seats for 60 minutes. | System | Must | `expires_at` equals creation time plus 60 minutes and all held resources reference the reservation. | Q-019, Q-040 |
| FR-013 | The system shall automatically assign one available physical seat in the requested cabin to each passenger on each flight-leg segment. | System | Must | The number of held assignments equals passengers multiplied by segments, with no duplicate seat per leg instance; keeping the same seat across consecutive legs is best effort. | Q-038 |
| FR-014 | The system shall expire an unpaid reservation after its hold deadline and release its resources exactly once. | System | Must | Repeated expiration attempts leave the reservation `EXPIRED` and do not increase availability beyond capacity. | Q-019, INV-05, INV-06 |
| FR-015 | A guest shall retrieve a reservation using its unique locator and a passenger surname. | Passenger, agency agent | Must | A matching pair returns the reservation; a mismatched pair does not disclose reservation data. | Q-037 |

## Payment, purchase, ticket, and cancellation requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-016 | The system shall record simulated payment attempts as `PENDING`, `APPROVED`, or `DECLINED` without accepting card data. | Payment simulator | Must | Stored input contains amount, COP currency, timestamp, synthetic reference, and idempotency key, but no PAN/CVV. | Q-017, Q-048 |
| FR-017 | An approved payment received before expiration shall atomically confirm the reservation and its seat assignments. | Payment simulator | Must | Payment, reservation, holds, and assignments reach consistent approved/confirmed states in one transaction. | Q-019, Q-040 |
| FR-018 | Confirming a purchase shall issue exactly one immutable ticket per passenger and one ticket coupon per itinerary segment. | System | Must | For P passengers and S segments, confirmation produces P tickets and P × S coupons once, including on retries. | Q-016, INV-11 |
| FR-019 | A declined payment shall mark the reservation `PAYMENT_FAILED` and release all inventory exactly once. | Payment simulator | Must | No ticket is issued and a repeated decline cannot release capacity twice. | Q-040, Q-043 |
| FR-020 | The system shall reject approval received after reservation expiration. | Payment simulator | Must | A late approval cannot confirm, re-hold seats, or issue tickets. | Q-019 |
| FR-021 | Payment processing shall be idempotent by operation reference. | Payment simulator | Must | Retrying an approval produces no duplicate approved payment, ticket, coupon, or inventory transition. | Q-044, Q-048 |
| FR-022 | A passenger or agency agent shall cancel an entire `CONFIRMED` reservation until 24 hours before first-segment departure. | Passenger, agency agent | Must | A valid request changes the reservation to `CANCELLED`, voids all tickets/coupons, releases all inventory, and records a simulated 90% refund. | Q-022, Q-041 |
| FR-023 | Cancelling a `PENDING_PAYMENT` reservation shall release its resources without creating a refund or tickets. | Passenger, agency agent | Must | The resulting state is `CANCELLED` and all held inventory is available. | Q-022, Q-040–Q-041 |
| FR-024 | Cancellation shall be idempotent and preserve history rather than physically deleting reservations, payments, or tickets. | System | Must | Repeating cancellation returns the prior result and does not duplicate refunds or releases. | Q-041, Q-044, INV-12 |
| FR-025 | The MVP shall reject partial passenger/segment cancellation and date/flight changes as unsupported operations. | Passenger, agency agent | Must | Requests return a stable business error and cause no state change. | Q-022, Q-041–Q-042 |

## Agency, administration, and airport requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-026 | An agency reservation shall use the same availability and booking rules while recording channel, agency, and agent attribution. | Agency agent | Must | Every agency-created reservation has `channel=AGENCY`, `agency_id`, and `agent_id`. | Q-049–Q-050 |
| FR-027 | The system shall calculate a 5% agency commission on fare before taxes without changing the passenger total. | System | Should | The stored commission reconciles to the fare components and appears in agency analytics. | Q-049 |
| FR-028 | An administrator shall maintain airports, aircraft, seats, routes, recurring flights and their ordered scheduled legs, dated flight/leg instances, cabin inventory, and fares. | Administrator | Must | Valid create/read/update operations succeed; operations violating leg order, references, or active inventory are rejected. | Q-016, Q-029, Q-039 |
| FR-029 | An administrator shall transition a flight instance through its allowed operational states. | Administrator | Should | Illegal transitions are rejected; only `SCHEDULED` and `DELAYED` instances remain sellable before cutoff. | Q-030 |
| FR-030 | The system shall reject an aircraft substitution when cabin capacity or seat mapping cannot accommodate all active assignments. | Administrator | Must | A rejected substitution causes no aircraft, inventory, reservation, or seat changes. | Q-039, INV-10 |
| FR-031 | Airport staff shall retrieve a read-only manifest of confirmed passengers and assigned seats for a flight-leg instance. | Airport staff | Should | The response excludes pending, expired, failed, and cancelled reservations and exposes no payment details. | Q-015, Q-029 |

## Pricing requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-032 | The system shall calculate fare per passenger and segment from route/cabin base fare, advance-purchase multiplier, airport fee, and simulated tax. | System | Must | Tests cover >30 days = 0.80, 7–30 days = 1.00, <7 days = 1.25, and business multiplier = 1.80. | Q-045, Q-047 |
| FR-033 | The system shall store monetary amounts in COP using fixed decimal arithmetic and two-decimal half-up rounding. | System | Must | No money field or calculation uses binary floating point; boundary rounding tests pass. | Q-046 |
| FR-034 | The reservation shall preserve an immutable price breakdown per passenger and segment. | System | Must | Subsequent fare changes do not alter existing reservation, ticket, payment, or analytical amounts. | Q-035, Q-045, Q-047, INV-07 |

## Audit and analytical requirements

| ID | Description | Actor | Priority | Acceptance criterion | Origin |
|---|---|---|---|---|---|
| FR-035 | The system shall record every reservation, payment, ticket, and inventory state transition with actor, timestamp, reason, previous state, new state, and correlation identifier. | System | Must | A complete reservation history can be reconstructed without relying only on application logs. | Q-040, Q-048 |
| FR-036 | The ETL shall load approved revenue, refunds, voluntary cancellations, and route/cabin occupancy snapshots from OLTP into PostgreSQL OLAP. | ETL process | Must | A controlled source dataset reconciles with OLAP counts and monetary totals after a run. | Q-023–Q-024 |
| FR-037 | The analytical model shall distinguish voluntary cancellation from expiration and payment failure. | ETL process, analyst | Must | Cancellation metrics exclude `EXPIRED` and `PAYMENT_FAILED` reservations. | Q-023, INV-09 |
| FR-038 | The analytical layer shall prepare gross/net revenue by fare/cabin, cancellation patterns by route/date/channel/advance-purchase band, and confirmed occupancy by route/cabin. | Analyst | Must | Seeded scenarios produce reconciled dimensional facts verified by automated SQL assertions; dashboards and interpretation remain out of scope. | Q-023, Q-045, Q-049 |
| FR-039 | The analytical ETL shall execute automatically every hour through an activated AWS Glue scheduled trigger. | ETL process | Must | CloudFormation defines `cron(0 * * * ? *)`; deployment activates it after uploading the job, and each run records its data cutoff. | Q-024, Q-026 |
| FR-040 | AWS Glue Data Catalog shall contain metadata for the selected OLTP and OLAP PostgreSQL tables. | ETL process, analyst | Must | Automated or exported evidence identifies both catalog databases and their expected tables/columns. | OBL-12, Q-026 |

## Explicitly excluded from the MVP

| ID | Excluded capability | Rationale |
|---|---|---|
| OUT-01 | Real payment gateway and card processing | Avoids PCI scope and is not required for the academic implementation. |
| OUT-02 | Round-trip reservation in one transaction | A return can be represented as a second one-way reservation. |
| OUT-03 | More than one connection | The MVP demonstrates multi-leg behavior with two segments. |
| OUT-04 | Partial cancellation and itinerary changes | They substantially expand pricing, inventory, refund, and audit rules. |
| OUT-05 | Check-in and visual seat selection | Seats are assigned automatically when inventory is held. |
| OUT-06 | Baggage, meals, loyalty, promotional coupons, codeshares, and notifications | Not required by the critical reservation path; flight coupons belonging to issued tickets remain in scope. |
| OUT-07 | Multiple currencies and passenger age categories | The MVP uses COP and assumes every passenger consumes one seat. |
| OUT-08 | Production-grade authentication and authorization | Demonstration identities are controlled test fixtures; the limitation is documented. |

## Team decisions requiring explicit confirmation

The following values were inferred to turn incomplete answers into a testable baseline. The team should approve or replace them before schema implementation:

| Decision | Proposed value |
|---|---|
| Sales horizon and cutoff | 180 days; sales close 60 minutes before departure. |
| Maximum itinerary | Two segments / one connection. |
| Connection window | 45 minutes to 6 hours, same airport. |
| Reservation size | 1–9 passengers, one cabin and itinerary. |
| Seat handling | Automatic seat assignment during the one-hour hold. |
| Cancellation | Entire reservation, until 24 hours before departure. |
| Cancellation refund | Simulated 90% refund / 10% penalty. |
| Fare multipliers | 0.80, 1.00, 1.25 by advance band; business × 1.80. |
| Simulated tax and commission | 10% academic tax; 5% agency commission before tax. |
| Currency | COP only. |
| Authentication | Guest lookup; test identities for privileged actors. |

## Traceability and change rule

Each implementation test shall reference at least one `FR-xxx` identifier. If implementation forces a different rule, the corresponding answer in the definition document and this requirement must be changed together, with the deviation recorded in an ADR or change log.
