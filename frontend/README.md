# Skyline MVP frontend

This is a dependency-free, static browser client. It can be served by FastAPI's static-files mount or any ordinary web server:

```bash
cd frontend && python3 -m http.server 8080
```

The client calls the same-origin `/api/v1`. Runtime data is never mocked: unavailable endpoints and structured API errors are shown to the user. Serve it through FastAPI in deployment (or use `python3 -m http.server` only for static review).

Implemented flow: live one-way search (direct/one connection), itinerary selection, 1–9 passenger capture, `DIRECT` or `AGENCY` attribution, idempotent reservation hold, expiration display, simulated approval/decline, lookup by locator and surname, tickets/coupons/seats display, and total cancellation.

## HTTP contract consumed

* `GET /api/v1/flights/search?origin=&destination=&date=&passengers=&cabin=`
* `POST /api/v1/reservations` with `Idempotency-Key`
* `POST /api/v1/reservations/{id}/payments` (`approved`, `operation_reference`)
* `GET /api/v1/reservations/{locator}?surname=`
* `POST /api/v1/reservations/{id}/cancel`
* `GET /api/v1/reservations/{id}/tickets`

Search responses may be an array or `{items|results|itineraries|data: [...]}`. Reservation responses may be wrapped in `{reservation: ...}`. This tolerance only handles envelope shape; it does not supply data.

## Adapter notes

The adapter sends only persisted fields: `leg_ids`, `cabin`, `passengers` (`given_name`, `surname`), `channel`, and (for `AGENCY`) `agency_id`/`agent_id`. It deliberately does not request buyer contact data or personal documents because those are not part of the API contract. Payment returns a payment result rather than the updated reservation, so the client derives the resulting state and calls `/tickets` separately. Missing ticket or seat fields are displayed as unavailable rather than fabricated.

For an agency hold, the client uses the canonical demo role `AGENCY_AGENT` and sends `X-Demo-Actor-Id` (agent ID) plus `X-Demo-Agency-Id` (agency ID) on the hold, payment, ticket, and cancellation requests. The seeded demonstration IDs are `agent-7` and `agency-1`; enter those values when running the agency flow. No admin role is exposed by this UI.

The static checks can be run with `node test.js`; no npm install or build step is required. Same-origin hosting is required by the included CSP and is the deployment default.
