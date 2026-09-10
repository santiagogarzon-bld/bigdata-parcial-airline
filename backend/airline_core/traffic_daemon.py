"""Long-running, human-paced traffic controller targeting a load factor per flight leg."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import signal
import sys
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from airline_core.simulation import (
    ApiClient,
    Config,
    Metrics,
    SimulationError,
    UserResult,
    simulate_user,
)

JsonValue = Any
ADMIN_HEADERS = {"X-Demo-Actor-Id": "demo-admin", "X-Demo-Role": "ADMIN"}


@dataclass(frozen=True)
class TargetLeg:
    leg_id: str
    origin: str
    destination: str
    travel_date: str
    cabin: str
    capacity: int
    confirmed: int
    departure_at: str

    @property
    def key(self) -> str:
        return f"{self.leg_id}:{self.cabin}"

    def gap(self, target_percent: float) -> int:
        return max(0, desired_seats(self, target_percent) - self.confirmed)


def row_target_percent(target: TargetLeg, average_percent: float) -> float:
    """Give flights stable, varied targets while keeping the fleet near the requested mean."""
    bucket = hashlib.sha256(target.leg_id.encode()).digest()[0] % 5
    return max(1, min(99, average_percent + (-6, -3, 0, 3, 6)[bucket]))


def desired_seats(target: TargetLeg, average_percent: float) -> int:
    return math.ceil(target.capacity * row_target_percent(target, average_percent) / 100)


def _departure(target: TargetLeg) -> datetime:
    return datetime.fromisoformat(target.departure_at)


def allows_confirmed_cancellation(target: TargetLeg, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    return _departure(target) - current >= timedelta(hours=24)


@dataclass(frozen=True)
class DaemonConfig:
    base_url: str
    start_date: date
    end_date: date
    routes: tuple[tuple[str, str], ...]
    target_percent: float
    concurrency: int
    arrival_min: float
    arrival_max: float
    think_min: float
    think_max: float
    scan_seconds: float
    seed: int
    timeout: float
    duration_hours: float


def parse_routes(value: str) -> tuple[tuple[str, str], ...]:
    routes: list[tuple[str, str]] = []
    for item in value.split(","):
        parts = item.strip().upper().split("-")
        if len(parts) != 2 or any(len(code) != 3 for code in parts):
            raise SimulationError("--routes must use ORG-DST comma-separated pairs")
        routes.append((parts[0], parts[1]))
    if not routes:
        raise SimulationError("--routes cannot be empty")
    return tuple(routes)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run human-paced synthetic traffic until every flight approaches a target load."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--start-date", default="2026-09-11")
    parser.add_argument("--end-date", default="2026-09-20")
    parser.add_argument("--routes", default="BOG-MDE,MDE-BOG,MDE-CLO,CLO-BOG")
    parser.add_argument("--target-percent", type=float, default=30)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--arrival-min-seconds", type=float, default=10)
    parser.add_argument("--arrival-max-seconds", type=float, default=25)
    parser.add_argument("--think-min-seconds", type=float, default=5)
    parser.add_argument("--think-max-seconds", type=float, default=45)
    parser.add_argument("--scan-seconds", type=float, default=300)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=0,
        help="Stop after this many hours; zero keeps running.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> DaemonConfig:
    try:
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
    except ValueError as exc:
        raise SimulationError("dates must use YYYY-MM-DD") from exc
    if end_date < start_date:
        raise SimulationError("--end-date cannot precede --start-date")
    if not 0 < args.target_percent < 100:
        raise SimulationError("--target-percent must be between 0 and 100")
    if not 1 <= args.concurrency <= 100:
        raise SimulationError("--concurrency must be between 1 and 100")
    ranges = (
        (args.arrival_min_seconds, args.arrival_max_seconds, "arrival"),
        (args.think_min_seconds, args.think_max_seconds, "think"),
    )
    for minimum, maximum, label in ranges:
        if minimum < 0 or maximum < minimum:
            raise SimulationError(f"{label} seconds must satisfy 0 <= min <= max")
    if args.scan_seconds < 10 or args.timeout <= 0 or args.duration_hours < 0:
        raise SimulationError("scan must be >= 10s; timeout positive; duration nonnegative")
    return DaemonConfig(
        base_url=args.base_url.rstrip("/"),
        start_date=start_date,
        end_date=end_date,
        routes=parse_routes(args.routes),
        target_percent=args.target_percent,
        concurrency=args.concurrency,
        arrival_min=args.arrival_min_seconds,
        arrival_max=args.arrival_max_seconds,
        think_min=args.think_min_seconds,
        think_max=args.think_max_seconds,
        scan_seconds=args.scan_seconds,
        seed=args.seed,
        timeout=args.timeout,
        duration_hours=args.duration_hours,
    )


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def scan_targets(client: ApiClient, config: DaemonConfig) -> list[TargetLeg]:
    inventory_rows = client.request(
        "controller_inventory",
        "GET",
        "/api/v1/admin/inventory",
        query={"limit": 500},
        headers=ADMIN_HEADERS,
    )
    if not isinstance(inventory_rows, list):
        raise SimulationError("admin inventory response was not a list")
    inventories = {
        (str(row["flight_leg_instance_id"]), str(row["cabin"])): row for row in inventory_rows
    }
    discovered: dict[tuple[str, str], TargetLeg] = {}
    for travel_date in _dates(config.start_date, config.end_date):
        for origin, destination in config.routes:
            for cabin in ("ECONOMY", "BUSINESS"):
                flights = client.request(
                    "controller_search",
                    "GET",
                    "/api/v1/flights/search",
                    query={
                        "origin": origin,
                        "destination": destination,
                        "date": travel_date.isoformat(),
                        "passengers": 1,
                        "cabin": cabin,
                        "max_stops": 0,
                    },
                )
                if not isinstance(flights, list):
                    continue
                for itinerary in flights:
                    leg_ids = itinerary.get("leg_ids", [])
                    segments = itinerary.get("segments", [])
                    if len(leg_ids) != 1 or len(segments) != 1:
                        continue
                    leg_id = str(leg_ids[0])
                    inventory = inventories.get((leg_id, cabin))
                    if inventory is None:
                        continue
                    discovered[(leg_id, cabin)] = TargetLeg(
                        leg_id=leg_id,
                        origin=origin,
                        destination=destination,
                        travel_date=travel_date.isoformat(),
                        cabin=cabin,
                        capacity=int(inventory["capacity"]),
                        confirmed=int(inventory["confirmed"]),
                        departure_at=str(segments[0]["departure_at"]),
                    )
    return list(discovered.values())


def progress(targets: list[TargetLeg], target_percent: float) -> dict[str, JsonValue]:
    target_seats = sum(desired_seats(item, target_percent) for item in targets)
    credited = sum(min(item.confirmed, desired_seats(item, target_percent)) for item in targets)
    complete = sum(item.gap(target_percent) == 0 for item in targets)
    return {
        "event": "inventory_scan",
        "target_percent": target_percent,
        "target_rows": len(targets),
        "rows_at_target": complete,
        "confirmed_toward_target": credited,
        "target_seats": target_seats,
        "completion_percent": round(credited * 100 / target_seats, 2) if target_seats else 0,
    }


def user_config(
    daemon: DaemonConfig,
    target: TargetLeg,
    user_number: int,
    filling: bool,
    now: datetime | None = None,
) -> Config:
    can_cancel_confirmed = allows_confirmed_cancellation(target, now)
    if filling:
        cancel_hold, decline, confirmed = (10, 15, 60)
        if not can_cancel_confirmed:
            cancel_hold, decline, confirmed = (15, 20, 60)
        search_only = 5
    else:
        search_only, cancel_hold, decline, confirmed = (20, 30, 30, 0)
        if not can_cancel_confirmed:
            search_only, cancel_hold, decline = (20, 40, 40)
    return Config(
        base_url=daemon.base_url,
        users=1,
        concurrency=1,
        seed=daemon.seed + user_number,
        timeout=daemon.timeout,
        travel_date=target.travel_date,
        origin=target.origin,
        destinations=(target.destination,),
        target_leg_id=target.leg_id,
        booking_retries=3,
        min_pause=daemon.think_min,
        max_pause=daemon.think_max,
        agency_percent=25,
        business_percent=100 if target.cabin == "BUSINESS" else 0,
        two_passenger_percent=0 if target.cabin == "BUSINESS" else 30,
        replay_percent=5,
        search_only_percent=search_only,
        pending_percent=0,
        cancel_hold_percent=cancel_hold,
        decline_percent=decline,
        confirmed_percent=confirmed,
        quiet=True,
    )


def choose_target(
    rng: random.Random,
    targets: list[TargetLeg],
    target_percent: float,
    planned: Counter[str],
) -> tuple[TargetLeg, bool] | None:
    under_target = [item for item in targets if item.gap(target_percent) - planned[item.key] > 0]
    if under_target:
        weights = [
            max(1, item.gap(target_percent) - planned[item.key])
            * max(
                1.0,
                240.0
                / max(
                    1.0,
                    (_departure(item) - datetime.now(UTC)).total_seconds() / 3600,
                ),
            )
            for item in under_target
        ]
        return rng.choices(under_target, weights=weights, k=1)[0], True
    if targets and all(item.gap(target_percent) == 0 for item in targets):
        return rng.choice(targets), False
    return None


def run(argv: list[str] | None = None) -> int:
    try:
        daemon = config_from_args(parse_args(argv))
    except SimulationError as exc:
        print(f"configuration failed: {exc}", file=sys.stderr, flush=True)
        return 2
    metrics = Metrics()
    client = ApiClient(daemon.base_url, daemon.timeout, metrics)
    try:
        health = client.request("controller_health", "GET", "/api/v1/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise SimulationError("API healthcheck did not return status=ok")
    except SimulationError as exc:
        print(f"preflight failed: {exc}", file=sys.stderr, flush=True)
        return 2

    stopping = threading.Event()
    start_users = threading.Event()
    start_users.set()

    def stop(_: int, __: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    rng = random.Random(daemon.seed)
    active: dict[Future[UserResult], str] = {}
    planned: Counter[str] = Counter()
    targets: list[TargetLeg] = []
    next_scan = 0.0
    started = time.monotonic()
    user_number = 0

    executor = ThreadPoolExecutor(max_workers=daemon.concurrency)
    try:
        while not stopping.is_set():
            if daemon.duration_hours and time.monotonic() - started >= daemon.duration_hours * 3600:
                break
            for future in [item for item in active if item.done()]:
                leg_id = active.pop(future)
                try:
                    result = future.result()
                    print(
                        json.dumps(
                            {
                                "event": "user_complete",
                                "user": result.user_number,
                                "target": leg_id,
                                "scenario": result.scenario,
                                "outcome": result.outcome,
                            }
                        ),
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001 - daemon isolates failed users
                    print(
                        json.dumps({"event": "user_failed", "target": leg_id, "error": str(exc)}),
                        file=sys.stderr,
                        flush=True,
                    )
            now = time.monotonic()
            if now >= next_scan:
                try:
                    targets = scan_targets(client, daemon)
                    print(
                        json.dumps(progress(targets, daemon.target_percent)),
                        flush=True,
                    )
                    planned = Counter(active.values())
                    next_scan = now + daemon.scan_seconds
                except SimulationError as exc:
                    print(
                        json.dumps({"event": "scan_failed", "error": str(exc)}),
                        file=sys.stderr,
                        flush=True,
                    )
                    stopping.wait(min(60, daemon.scan_seconds))
                    continue
            if len(active) >= daemon.concurrency:
                stopping.wait(1)
                continue
            selected = choose_target(rng, targets, daemon.target_percent, planned)
            if selected is None:
                stopping.wait(min(10, max(1, next_scan - time.monotonic())))
                continue
            target, filling = selected
            user_number += 1
            future = executor.submit(
                simulate_user,
                user_number,
                user_config(daemon, target, user_number, filling),
                client,
                start_users,
            )
            active[future] = target.key
            planned[target.key] += 1
            stopping.wait(rng.uniform(daemon.arrival_min, daemon.arrival_max))
    finally:
        stopping.set()
        executor.shutdown(wait=True, cancel_futures=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
