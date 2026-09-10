from datetime import UTC, date, datetime

from airline_core.traffic_daemon import (
    DaemonConfig,
    TargetLeg,
    allows_confirmed_cancellation,
    desired_seats,
    progress,
    row_target_percent,
    user_config,
)


def target(**overrides: object) -> TargetLeg:
    values: dict[str, object] = {
        "leg_id": "leg-1",
        "origin": "BOG",
        "destination": "MDE",
        "travel_date": "2026-09-20",
        "cabin": "ECONOMY",
        "capacity": 150,
        "confirmed": 0,
        "departure_at": "2026-09-20T12:00:00+00:00",
    }
    values.update(overrides)
    return TargetLeg(**values)  # type: ignore[arg-type]


def daemon() -> DaemonConfig:
    return DaemonConfig(
        base_url="http://example.test",
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 20),
        routes=(("BOG", "MDE"),),
        target_percent=30,
        concurrency=8,
        arrival_min=10,
        arrival_max=25,
        think_min=5,
        think_max=45,
        scan_seconds=300,
        seed=1,
        timeout=15,
        duration_hours=0,
    )


def test_per_leg_targets_are_stable_and_close_to_average() -> None:
    rows = [target(leg_id=f"leg-{number}") for number in range(20)]
    percentages = [row_target_percent(row, 30) for row in rows]

    assert percentages == [row_target_percent(row, 30) for row in rows]
    assert set(percentages).issubset({24, 27, 30, 33, 36})
    assert len(set(percentages)) > 1
    assert all(36 <= desired_seats(row, 30) <= 54 for row in rows)


def test_progress_credits_each_row_only_to_its_varied_target() -> None:
    rows = [target(leg_id=f"leg-{number}", confirmed=150) for number in range(5)]
    report = progress(rows, 30)

    assert report["target_seats"] == sum(desired_seats(row, 30) for row in rows)
    assert report["confirmed_toward_target"] == report["target_seats"]
    assert report["completion_percent"] == 100


def test_near_departure_never_attempts_a_confirmed_cancellation() -> None:
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    near = target(departure_at="2026-09-11T11:00:00+00:00")
    far = target(departure_at="2026-09-12T13:00:00+00:00")

    assert not allows_confirmed_cancellation(near, now)
    assert allows_confirmed_cancellation(far, now)
    near_config = user_config(daemon(), near, user_number=1, filling=True, now=now)
    far_config = user_config(daemon(), far, user_number=1, filling=True, now=now)
    assert (
        sum(
            (
                near_config.search_only_percent,
                near_config.cancel_hold_percent,
                near_config.decline_percent,
                near_config.confirmed_percent,
            )
        )
        == 100
    )
    assert (
        sum(
            (
                far_config.search_only_percent,
                far_config.cancel_hold_percent,
                far_config.decline_percent,
                far_config.confirmed_percent,
            )
        )
        == 90
    )
