# Data dictionary (OLTP)

Sensitivity: `public` operational metadata; `internal` commercial/audit metadata; `personal` synthetic or real passenger identity. No payment-card fields exist.

| Tables / columns | Type, nullability, keys | Meaning / sensitivity |
|---|---|---|
| `airports.code`, `iana_zone`, `name` | `varchar(3/64/120)`, code PK, zone non-null | IATA airport and IANA zone; public |
| `cabins.code`, `sort_order`, `active` | `varchar`, `int`, `bool`; code PK | Cabin catalog; public |
| `aircraft_types`, `aircraft`, `seats` | UUID/string PKs; FKs restrict; seat `(aircraft,label)` unique | Equipment and physical seats; internal |
| `routes`, `scheduled_flights`, `scheduled_legs` | UUID PKs; airport/FK references; flight/leg sequence unique | Commercial schedule and non-negative base prices; public/internal |
| `flight_instances`, `flight_leg_instances` | UUID PKs; `timestamptz` non-null; sequence unique | Dated operations and ordered legs; internal |
| `inventories.capacity/held/confirmed` | `int` non-null; `(leg,cabin)` unique/check | Authoritative cabin inventory; internal |
| `reservations` | UUID PK; locator unique; UTC dates; `numeric(14,2)` | Commercial state/idempotency/pricing total; internal |
| `itineraries`, `itinerary_segments` | UUID PK; reservation 1:1; order unique | Ordered itinerary; internal |
| `passengers.given_name/surname` | `varchar(100)` non-null; reservation FK | Passenger identity; personal |
| `reservation_items` | UUID PK; passenger/leg unique; active-seat partial unique; numeric snapshot | Passenger segment, seat, immutable quote; personal/internal |
| `payments`, `refunds` | UUID PK; synthetic operation ref unique; numeric COP | Simulated payment/refund history; internal, no PCI data |
| `tickets`, `coupons` | UUID PK; ticket number unique; ticket/leg unique | Issued/void commercial documents; internal |
| `agencies`, `agents` | string natural PK; agent→agency FK | Sales attribution; internal |
| `fare_rules`, `operational_settings` | string natural PK; decimal/text values | Versioned required policy catalog; public/internal |
| `audit_events`, `idempotency_records` | UUID PK; UTC timestamp; correlation/hash | Audit and safe retry history; internal |
