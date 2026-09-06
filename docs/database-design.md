# OLTP database design

The application keeps the existing `public` schema for compatibility. Alembic is the sole DDL authority; there is no competing `schema.sql`.

Inventory is exactly one row per `flight_leg_instances × cabin`. `capacity >= held + confirmed` is a database check and booking locks inventory in canonical order. A partial unique index permits one active `(leg, seat)` assignment while released historical assignments remain; the same physical seat can therefore appear in later legs.

Commercial history uses restrictive foreign keys: reservations, payments, tickets, coupons, refunds and audit events are state transitioned rather than deleted. `reservation_items` is the immutable passenger-segment/price snapshot. `itineraries` and `itinerary_segments` give each reservation an ordered itinerary; their unique keys prevent duplicate legs or segment order. Money is `NUMERIC`, times are `timestamptz`, airport zones are IANA strings.

Critical indexes are the active seat partial unique index, inventory natural unique key, `reservation_items(reservation_id, sequence)`, payment/reservation time, and audit entity/time. Named checks constrain amounts, cabin, payment/reservation/ticket states, IATA codes and leg order. State strings are CHECKs rather than duplicated state lookup tables.

```mermaid
erDiagram
  AIRPORT ||--o{ ROUTE : origin_destination
  ROUTE ||--o{ SCHEDULED_FLIGHT : groups
  SCHEDULED_FLIGHT ||--o{ SCHEDULED_LEG : ordered
  SCHEDULED_FLIGHT ||--o{ FLIGHT_INSTANCE : occurs
  FLIGHT_INSTANCE ||--o{ FLIGHT_LEG_INSTANCE : ordered
  FLIGHT_LEG_INSTANCE ||--o{ INVENTORY : cabin
  AIRCRAFT_TYPE ||--o{ AIRCRAFT : classifies
  AIRCRAFT ||--o{ SEAT : contains
  RESERVATION ||--|| ITINERARY : owns
  ITINERARY ||--o{ ITINERARY_SEGMENT : ordered
  RESERVATION ||--o{ PASSENGER : includes
  PASSENGER ||--o{ RESERVATION_ITEM : travels
  FLIGHT_LEG_INSTANCE ||--o{ RESERVATION_ITEM : assigned
  RESERVATION ||--o{ PAYMENT : attempts
  PAYMENT ||--o| REFUND : reverses
  PASSENGER ||--o{ TICKET : receives
  TICKET ||--o{ COUPON : contains
```
