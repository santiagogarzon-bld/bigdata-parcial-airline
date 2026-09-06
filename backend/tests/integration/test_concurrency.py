"""Real PostgreSQL contention tests; SQLite is intentionally never a substitute here."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from airline_core.application.service import BookingService, CreateReservation, PassengerInput
from airline_core.domain.errors import InventoryUnavailable
from airline_core.domain.types import Cabin, Channel
from airline_core.persistence.models import Base, FlightLegInstance, Inventory, ReservationItem
from airline_core.persistence.seeds import seed

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]
ITERATIONS = int(os.getenv("AIRLINE_CONCURRENCY_ITERATIONS", "1"))


@pytest.mark.parametrize("two_segments", [False, True], ids=["direct", "two_segment_bottleneck"])
def test_last_unit_has_one_winner_20_real_postgres(pg_engine, two_segments):
    """Use ``AIRLINE_CONCURRENCY_ITERATIONS=30`` for the required full 30×20 run."""
    Session = sessionmaker(pg_engine, expire_on_commit=False)
    for run in range(ITERATIONS):
        Base.metadata.drop_all(pg_engine)
        Base.metadata.create_all(pg_engine)
        with Session.begin() as s:
            seed(s)
        with Session() as s:
            legs = list(
                s.scalars(select(FlightLegInstance).order_by(FlightLegInstance.departure_at))
            )
            chosen = (legs[1].id, legs[2].id) if two_segments else (legs[0].id,)
            bottleneck = chosen[-1]
            inv = s.scalar(
                select(Inventory).where(
                    Inventory.flight_leg_instance_id == bottleneck, Inventory.cabin == Cabin.ECONOMY
                )
            )
            assert inv is not None
            inv.capacity = 1
            s.commit()
        gate = Barrier(20)

        def worker(n: int, _gate=gate, _run=run, _chosen=chosen) -> str:
            try:
                with Session.begin() as s:
                    _gate.wait(timeout=10)
                    BookingService(s).create(
                        CreateReservation(
                            actor_id=f"actor-{n}",
                            channel=Channel.DIRECT,
                            idempotency_key=f"{_run}-{n}",
                            leg_ids=_chosen,
                            cabin=Cabin.ECONOMY,
                            passengers=(PassengerInput("P", str(n)),),
                            correlation_id="concurrent",
                        )
                    )
                return "winner"
            except InventoryUnavailable:
                return "conflict"

        with ThreadPoolExecutor(max_workers=20) as executor:
            result = list(executor.map(worker, range(20)))
        assert result.count("winner") == 1 and result.count("conflict") == 19
        with Session() as s:
            inv = s.scalar(
                select(Inventory).where(
                    Inventory.flight_leg_instance_id == bottleneck, Inventory.cabin == Cabin.ECONOMY
                )
            )
            assert inv.capacity - inv.held - inv.confirmed == 0
            items = list(
                s.scalars(
                    select(ReservationItem).where(
                        ReservationItem.flight_leg_instance_id == bottleneck
                    )
                )
            )
            assert len({x.seat_id for x in items}) == len(items) == 1
