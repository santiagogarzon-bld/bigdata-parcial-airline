from __future__ import annotations

import random

import pytest

from airline_core.simulation import (
    Config,
    Metrics,
    SimulationError,
    choose_scenario,
    config_from_args,
    parse_args,
    percentile,
    reservation_payload,
    summary,
)


def config(**overrides):
    values = {
        "base_url": "http://example.test",
        "users": 10,
        "concurrency": 2,
        "seed": 7,
        "timeout": 1.0,
        "travel_date": "2026-09-20",
        "destinations": ("MDE", "CLO"),
        "booking_retries": 3,
        "max_pause": 0,
        "agency_percent": 0,
        "business_percent": 0,
        "two_passenger_percent": 0,
        "replay_percent": 0,
        "search_only_percent": 10,
        "pending_percent": 10,
        "cancel_hold_percent": 20,
        "decline_percent": 20,
        "confirmed_percent": 10,
        "quiet": True,
    }
    values.update(overrides)
    return Config(**values)


def test_scenario_selection_is_deterministic_and_complete() -> None:
    first = [choose_scenario(random.Random(seed), config()) for seed in range(100)]
    second = [choose_scenario(random.Random(seed), config()) for seed in range(100)]

    assert first == second
    assert set(first) == {
        "search_only",
        "pending",
        "cancel_hold",
        "declined",
        "confirmed",
        "confirmed_cancelled",
    }


def test_direct_and_agency_payloads_are_valid() -> None:
    direct, direct_headers, surname = reservation_payload(
        random.Random(1), config(), ["leg-1"], 12, "ECONOMY", 1
    )
    assert direct["channel"] == "DIRECT"
    assert direct["passengers"][0]["surname"] == surname
    assert "X-Demo-Role" not in direct_headers

    agency, agency_headers, _ = reservation_payload(
        random.Random(1), config(agency_percent=100), ["leg-1"], 12, "BUSINESS", 2
    )
    assert agency["channel"] == "AGENCY"
    assert agency["cabin"] == "BUSINESS"
    assert len(agency["passengers"]) == 2
    assert agency["agency_id"] == "agency-1"
    assert agency_headers["X-Demo-Role"] == "AGENCY_AGENT"


def test_argument_validation_and_percentile() -> None:
    args = parse_args(
        [
            "--travel-date",
            "2026-09-20",
            "--users",
            "4",
            "--concurrency",
            "2",
        ]
    )
    parsed = config_from_args(args)
    assert parsed.destinations == ("MDE", "CLO")
    assert percentile([10, 30, 20], 0.5) == 20

    invalid = parse_args(
        [
            "--travel-date",
            "2026-09-20",
            "--users",
            "2",
            "--concurrency",
            "3",
        ]
    )
    with pytest.raises(SimulationError, match="concurrency"):
        config_from_args(invalid)


def test_summary_reports_reservation_mix() -> None:
    metrics = Metrics()
    metrics.request("search", "200", 12.5)
    metrics.reservation_mix("AGENCY", "BUSINESS", "CLO", 2)
    metrics.finish("confirmed", "confirmed", True)

    report = summary(config(users=1, concurrency=1), metrics, 0.5)

    assert report["reservations_created"] == 1
    assert report["reservation_mix"] == {
        "channels": {"AGENCY": 1},
        "cabins": {"BUSINESS": 1},
        "destinations": {"CLO": 1},
        "party_sizes": {"2": 1},
    }
