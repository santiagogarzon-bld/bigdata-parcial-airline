"""Concurrent synthetic-user traffic generator for the public demo API."""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

JsonValue = Any
FIRST_NAMES = (
    "Ana",
    "Carlos",
    "Daniela",
    "Felipe",
    "Isabella",
    "Laura",
    "Mateo",
    "Sofia",
)
SURNAMES = (
    "Alvarez",
    "Castro",
    "Garcia",
    "Gomez",
    "Martinez",
    "Moreno",
    "Rodriguez",
    "Torres",
)


class SimulationError(RuntimeError):
    """A request or workflow failed."""


class ApiError(SimulationError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code


@dataclass
class Metrics:
    requests: Counter[str] = field(default_factory=Counter)
    statuses: Counter[str] = field(default_factory=Counter)
    scenarios: Counter[str] = field(default_factory=Counter)
    outcomes: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    channels: Counter[str] = field(default_factory=Counter)
    cabins: Counter[str] = field(default_factory=Counter)
    destinations: Counter[str] = field(default_factory=Counter)
    party_sizes: Counter[str] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    reservations_created: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def request(self, action: str, status: str, latency_ms: float) -> None:
        with self.lock:
            self.requests[action] += 1
            self.statuses[status] += 1
            self.latencies_ms.append(latency_ms)

    def error(self, category: str) -> None:
        with self.lock:
            self.errors[category] += 1

    def finish(self, scenario: str, outcome: str, created: bool) -> None:
        with self.lock:
            self.scenarios[scenario] += 1
            self.outcomes[outcome] += 1
            self.reservations_created += int(created)

    def reservation_mix(
        self,
        channel: str,
        cabin: str,
        destination: str,
        party_size: int,
    ) -> None:
        with self.lock:
            self.channels[channel] += 1
            self.cabins[cabin] += 1
            self.destinations[destination] += 1
            self.party_sizes[str(party_size)] += 1


class ApiClient:
    def __init__(self, base_url: str, timeout: float, metrics: Metrics) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.metrics = metrics

    def request(
        self,
        action: str,
        method: str,
        path: str,
        *,
        query: dict[str, str | int] | None = None,
        body: dict[str, JsonValue] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JsonValue:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        request_headers = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                self.metrics.request(
                    action,
                    str(response.status),
                    (time.perf_counter() - started) * 1000,
                )
                return json.loads(payload) if payload else None
        except HTTPError as exc:
            payload = exc.read()
            self.metrics.request(
                action,
                str(exc.code),
                (time.perf_counter() - started) * 1000,
            )
            try:
                decoded = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                decoded = {}
            error = decoded.get("error", decoded.get("detail", {}))
            if not isinstance(error, dict):
                error = {}
            raise ApiError(
                exc.code,
                str(error.get("code", "HTTP_ERROR")),
                str(error.get("message", exc.reason)),
            ) from exc
        except (URLError, TimeoutError) as exc:
            self.metrics.request(
                action,
                "transport_error",
                (time.perf_counter() - started) * 1000,
            )
            raise SimulationError(f"transport error calling {path}: {exc}") from exc


@dataclass(frozen=True)
class Config:
    base_url: str
    users: int
    concurrency: int
    seed: int
    timeout: float
    travel_date: str
    origin: str
    destinations: tuple[str, ...]
    target_leg_id: str | None
    booking_retries: int
    min_pause: float
    max_pause: float
    agency_percent: int
    business_percent: int
    two_passenger_percent: int
    replay_percent: int
    search_only_percent: int
    pending_percent: int
    cancel_hold_percent: int
    decline_percent: int
    confirmed_percent: int
    quiet: bool


@dataclass(frozen=True)
class UserResult:
    user_number: int
    scenario: str
    outcome: str
    created: bool
    locator: str | None = None
    detail: str | None = None


def _chance(rng: random.Random, percent: int) -> bool:
    return rng.randrange(100) < percent


def choose_scenario(rng: random.Random, config: Config) -> str:
    value = rng.randrange(100)
    thresholds = (
        ("search_only", config.search_only_percent),
        ("pending", config.pending_percent),
        ("cancel_hold", config.cancel_hold_percent),
        ("declined", config.decline_percent),
        ("confirmed", config.confirmed_percent),
    )
    cumulative = 0
    for scenario, weight in thresholds:
        cumulative += weight
        if value < cumulative:
            return scenario
    return "confirmed_cancelled"


def reservation_payload(
    rng: random.Random,
    config: Config,
    leg_ids: list[str],
    user_number: int,
    cabin: str,
    passenger_count: int,
) -> tuple[dict[str, JsonValue], dict[str, str], str]:
    agency = _chance(rng, config.agency_percent)
    surname = f"{rng.choice(SURNAMES)}Sim{user_number:05d}"
    people = [
        {
            "given_name": f"{rng.choice(FIRST_NAMES)}{position + 1}",
            "surname": surname,
        }
        for position in range(passenger_count)
    ]
    body: dict[str, JsonValue] = {
        "leg_ids": leg_ids,
        "cabin": cabin,
        "passengers": people,
        "channel": "AGENCY" if agency else "DIRECT",
    }
    headers = {
        "X-Correlation-Id": f"sim-create-{user_number}-{uuid4()}",
        "Idempotency-Key": f"sim-reservation-{config.seed}-{user_number}-{uuid4()}",
    }
    if agency:
        body.update({"agency_id": "agency-1", "agent_id": "agent-7"})
        headers.update(
            {
                "X-Demo-Actor-Id": "agent-7",
                "X-Demo-Role": "AGENCY_AGENT",
                "X-Demo-Agency-Id": "agency-1",
            }
        )
    return body, headers, surname


def discover_travel_date(client: ApiClient, search_days: int) -> str:
    local_today = datetime.now(ZoneInfo("America/Bogota")).date()
    for offset in range(search_days + 1):
        candidate = (local_today + timedelta(days=offset)).isoformat()
        flights = client.request(
            "discover",
            "GET",
            "/api/v1/flights/search",
            query={
                "origin": "BOG",
                "destination": "MDE",
                "date": candidate,
                "passengers": 1,
                "cabin": "ECONOMY",
                "max_stops": 1,
            },
        )
        if isinstance(flights, list) and flights:
            return candidate
    raise SimulationError(f"no BOG departure with inventory found in {search_days + 1} days")


def _pause(rng: random.Random, minimum: float, maximum: float) -> None:
    if maximum > 0:
        time.sleep(rng.uniform(minimum, maximum))


def _identity_headers(user_number: int) -> dict[str, str]:
    return {"X-Correlation-Id": f"sim-action-{user_number}-{uuid4()}"}


def _action_headers(user_number: int, reservation_headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value for key, value in reservation_headers.items() if key.startswith("X-Demo-")
    } | _identity_headers(user_number)


def simulate_user(
    user_number: int,
    config: Config,
    client: ApiClient,
    start: threading.Event,
) -> UserResult:
    rng = random.Random(config.seed + user_number * 104_729)
    scenario = choose_scenario(rng, config)
    start.wait()
    _pause(rng, config.min_pause, config.max_pause)

    if scenario == "search_only":
        destination = rng.choice(config.destinations)
        client.request(
            "search",
            "GET",
            "/api/v1/flights/search",
            query={
                "origin": config.origin,
                "destination": destination,
                "date": config.travel_date,
                "passengers": 1,
                "cabin": "ECONOMY",
                "max_stops": 1,
            },
        )
        return UserResult(user_number, scenario, "search_abandoned", False)

    last_error: str | None = None
    for attempt in range(config.booking_retries):
        destination_index = (rng.randrange(len(config.destinations)) + attempt) % len(
            config.destinations
        )
        destination = config.destinations[destination_index]
        cabin = "BUSINESS" if _chance(rng, config.business_percent) else "ECONOMY"
        passenger_count = 2 if _chance(rng, config.two_passenger_percent) else 1
        try:
            flights = client.request(
                "search",
                "GET",
                "/api/v1/flights/search",
                query={
                    "origin": config.origin,
                    "destination": destination,
                    "date": config.travel_date,
                    "passengers": passenger_count,
                    "cabin": cabin,
                    "max_stops": 1,
                },
            )
            if not isinstance(flights, list) or not flights:
                last_error = f"no inventory for {destination}/{cabin}/{passenger_count}"
                _pause(rng, config.min_pause, config.max_pause)
                continue
            selectable = flights
            if config.target_leg_id:
                selectable = [
                    item for item in flights if config.target_leg_id in item.get("leg_ids", [])
                ]
            if not selectable:
                last_error = f"target leg {config.target_leg_id} is no longer available"
                _pause(rng, config.min_pause, config.max_pause)
                continue
            itinerary = rng.choice(selectable)
            leg_ids = itinerary.get("leg_ids")
            if not isinstance(leg_ids, list) or not all(isinstance(item, str) for item in leg_ids):
                raise SimulationError("search response did not contain valid leg_ids")
            body, headers, surname = reservation_payload(
                rng,
                config,
                leg_ids,
                user_number,
                cabin,
                passenger_count,
            )
            reservation = client.request(
                "reserve",
                "POST",
                "/api/v1/reservations",
                body=body,
                headers=headers,
            )
            if not isinstance(reservation, dict):
                raise SimulationError("reservation response was not an object")
            client.metrics.reservation_mix(
                str(body["channel"]),
                cabin,
                destination,
                passenger_count,
            )
            if _chance(rng, config.replay_percent):
                client.request(
                    "reserve_replay",
                    "POST",
                    "/api/v1/reservations",
                    body=body,
                    headers=headers,
                )
            return finish_journey(
                user_number,
                scenario,
                rng,
                config,
                client,
                reservation,
                surname,
                headers,
            )
        except ApiError as exc:
            if exc.status == 409 and exc.code == "INVENTORY_UNAVAILABLE":
                client.metrics.error("inventory_conflict")
                last_error = str(exc)
                _pause(rng, config.min_pause, config.max_pause)
                continue
            raise
    return UserResult(
        user_number,
        scenario,
        "inventory_skipped",
        False,
        detail=last_error,
    )


def finish_journey(
    user_number: int,
    scenario: str,
    rng: random.Random,
    config: Config,
    client: ApiClient,
    reservation: dict[str, JsonValue],
    surname: str,
    reservation_headers: dict[str, str],
) -> UserResult:
    reservation_id = str(reservation["id"])
    locator = str(reservation["locator"])
    _pause(rng, config.min_pause, config.max_pause)
    client.request(
        "lookup",
        "GET",
        f"/api/v1/reservations/{locator}",
        query={"surname": surname},
        headers=_action_headers(user_number, reservation_headers),
    )

    if scenario == "pending":
        return UserResult(user_number, scenario, "pending", True, locator)
    if scenario == "cancel_hold":
        client.request(
            "cancel_hold",
            "POST",
            f"/api/v1/reservations/{reservation_id}/cancel",
            headers=_action_headers(user_number, reservation_headers),
        )
        return UserResult(user_number, scenario, "cancelled_hold", True, locator)

    approved = scenario in {"confirmed", "confirmed_cancelled"}
    payment_body = {
        "approved": approved,
        "operation_reference": f"sim-payment-{config.seed}-{user_number}-{uuid4()}",
    }
    client.request(
        "payment",
        "POST",
        f"/api/v1/reservations/{reservation_id}/payments",
        body=payment_body,
        headers=_action_headers(user_number, reservation_headers),
    )
    if _chance(rng, config.replay_percent):
        client.request(
            "payment_replay",
            "POST",
            f"/api/v1/reservations/{reservation_id}/payments",
            body=payment_body,
            headers=_action_headers(user_number, reservation_headers),
        )
    if not approved:
        return UserResult(user_number, scenario, "payment_declined", True, locator)

    tickets = client.request(
        "tickets",
        "GET",
        f"/api/v1/reservations/{reservation_id}/tickets",
        headers=_action_headers(user_number, reservation_headers),
    )
    if not isinstance(tickets, list) or not tickets:
        raise SimulationError("approved reservation did not issue tickets")
    leg_ids = reservation.get("segments", [])
    if isinstance(leg_ids, list) and leg_ids:
        first_leg = leg_ids[0]
        if isinstance(first_leg, dict) and first_leg.get("leg_id"):
            client.request(
                "manifest",
                "GET",
                f"/api/v1/flights/{first_leg['leg_id']}/manifest",
                headers={
                    "X-Demo-Actor-Id": "demo-airport",
                    "X-Demo-Role": "AIRPORT",
                    **_identity_headers(user_number),
                },
            )
    if scenario == "confirmed":
        return UserResult(user_number, scenario, "confirmed", True, locator)

    _pause(rng, config.min_pause, config.max_pause)
    client.request(
        "cancel_confirmed",
        "POST",
        f"/api/v1/reservations/{reservation_id}/cancel",
        headers=_action_headers(user_number, reservation_headers),
    )
    return UserResult(user_number, scenario, "cancelled_refunded", True, locator)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def summary(config: Config, metrics: Metrics, elapsed: float) -> dict[str, JsonValue]:
    with metrics.lock:
        latencies = list(metrics.latencies_ms)
        return {
            "configuration": {
                "base_url": config.base_url,
                "users": config.users,
                "concurrency": config.concurrency,
                "seed": config.seed,
                "travel_date": config.travel_date,
            },
            "elapsed_seconds": round(elapsed, 3),
            "users_per_second": round(config.users / elapsed, 2) if elapsed else 0,
            "reservations_created": metrics.reservations_created,
            "reservation_mix": {
                "channels": dict(sorted(metrics.channels.items())),
                "cabins": dict(sorted(metrics.cabins.items())),
                "destinations": dict(sorted(metrics.destinations.items())),
                "party_sizes": dict(sorted(metrics.party_sizes.items())),
            },
            "scenarios": dict(sorted(metrics.scenarios.items())),
            "outcomes": dict(sorted(metrics.outcomes.items())),
            "requests": {
                "total": sum(metrics.requests.values()),
                "by_action": dict(sorted(metrics.requests.items())),
                "by_status": dict(sorted(metrics.statuses.items())),
            },
            "expected_contention": dict(sorted(metrics.errors.items())),
            "latency_ms": {
                "p50": round(percentile(latencies, 0.50), 2),
                "p95": round(percentile(latencies, 0.95), 2),
                "max": round(max(latencies, default=0), 2),
            },
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate concurrent passenger and agency journeys through the airline API."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=25)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--travel-date")
    parser.add_argument("--search-days", type=int, default=30)
    parser.add_argument("--origin", default="BOG")
    parser.add_argument("--destinations", default="MDE,CLO")
    parser.add_argument("--target-leg-id")
    parser.add_argument("--booking-retries", type=int, default=5)
    parser.add_argument("--min-pause", type=float, default=0)
    parser.add_argument("--max-pause", type=float, default=0.25)
    parser.add_argument("--agency-percent", type=int, default=20)
    parser.add_argument("--business-percent", type=int, default=20)
    parser.add_argument("--two-passenger-percent", type=int, default=20)
    parser.add_argument("--replay-percent", type=int, default=10)
    parser.add_argument("--search-only-percent", type=int, default=10)
    parser.add_argument("--pending-percent", type=int, default=5)
    parser.add_argument("--cancel-hold-percent", type=int, default=20)
    parser.add_argument("--decline-percent", type=int, default=25)
    parser.add_argument("--confirmed-percent", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace, client: ApiClient | None = None) -> Config:
    if not 1 <= args.users <= 10_000:
        raise SimulationError("--users must be between 1 and 10000")
    if not 1 <= args.concurrency <= args.users:
        raise SimulationError("--concurrency must be between 1 and --users")
    if args.timeout <= 0 or args.min_pause < 0 or args.max_pause < args.min_pause:
        raise SimulationError("--timeout must be positive and pauses must satisfy 0 <= min <= max")
    if not 1 <= args.booking_retries <= 20:
        raise SimulationError("--booking-retries must be between 1 and 20")
    if not 0 <= args.search_days <= 365:
        raise SimulationError("--search-days must be between 0 and 365")
    percentages = (
        args.agency_percent,
        args.business_percent,
        args.two_passenger_percent,
        args.replay_percent,
        args.search_only_percent,
        args.pending_percent,
        args.cancel_hold_percent,
        args.decline_percent,
        args.confirmed_percent,
    )
    if any(value < 0 or value > 100 for value in percentages):
        raise SimulationError("all percentages must be between 0 and 100")
    retained_and_terminal = (
        args.search_only_percent
        + args.pending_percent
        + args.cancel_hold_percent
        + args.decline_percent
        + args.confirmed_percent
    )
    if retained_and_terminal > 100:
        raise SimulationError("scenario percentages cannot total more than 100")
    destinations = tuple(
        value.strip().upper() for value in args.destinations.split(",") if value.strip()
    )
    origin = args.origin.strip().upper()
    if len(origin) != 3:
        raise SimulationError("--origin must be one IATA code")
    if not destinations or any(len(value) != 3 for value in destinations):
        raise SimulationError("--destinations must contain comma-separated IATA codes")
    travel_date = args.travel_date
    if not travel_date:
        if client is None:
            raise SimulationError("an API client is required to discover --travel-date")
        travel_date = discover_travel_date(client, args.search_days)
    try:
        date.fromisoformat(travel_date)
    except ValueError as exc:
        raise SimulationError("--travel-date must use YYYY-MM-DD") from exc
    return Config(
        base_url=args.base_url.rstrip("/"),
        users=args.users,
        concurrency=args.concurrency,
        seed=args.seed,
        timeout=args.timeout,
        travel_date=travel_date,
        origin=origin,
        destinations=destinations,
        target_leg_id=args.target_leg_id,
        booking_retries=args.booking_retries,
        min_pause=args.min_pause,
        max_pause=args.max_pause,
        agency_percent=args.agency_percent,
        business_percent=args.business_percent,
        two_passenger_percent=args.two_passenger_percent,
        replay_percent=args.replay_percent,
        search_only_percent=args.search_only_percent,
        pending_percent=args.pending_percent,
        cancel_hold_percent=args.cancel_hold_percent,
        decline_percent=args.decline_percent,
        confirmed_percent=args.confirmed_percent,
        quiet=args.quiet,
    )


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metrics = Metrics()
    client = ApiClient(args.base_url, args.timeout, metrics)
    try:
        health = client.request("health", "GET", "/api/v1/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise SimulationError("API healthcheck did not return status=ok")
        config = config_from_args(args, client)
    except SimulationError as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2

    start = threading.Event()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {
            executor.submit(simulate_user, number, config, client, start): number
            for number in range(1, config.users + 1)
        }
        start.set()
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - isolate one synthetic user from the batch
                metrics.error(type(exc).__name__)
                result = UserResult(
                    futures[future],
                    "unknown",
                    "failed",
                    False,
                    detail=str(exc),
                )
            metrics.finish(result.scenario, result.outcome, result.created)
            if not config.quiet:
                suffix = f" locator={result.locator}" if result.locator else ""
                detail = f" detail={result.detail}" if result.detail else ""
                print(
                    f"user={result.user_number:05d} scenario={result.scenario} "
                    f"outcome={result.outcome}{suffix}{detail}",
                    file=sys.stderr,
                )

    report = summary(config, metrics, time.perf_counter() - started)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if metrics.outcomes["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
