from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from airline_core.application.service import CreateReservation, PassengerInput
from airline_core.domain.types import Cabin, Channel
from airline_core.persistence.database import database_url
from airline_core.persistence.models import Base, FlightLegInstance
from airline_core.persistence.seeds import seed


@pytest.fixture(scope="session")
def pg_engine():
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL required; run docker compose up -d")
    return engine


@pytest.fixture
def session(pg_engine):
    Base.metadata.drop_all(pg_engine)
    Base.metadata.create_all(pg_engine)
    Session = sessionmaker(pg_engine, expire_on_commit=False)
    with Session.begin() as s:
        seed(s)
    with Session() as s:
        yield s
    s.close()


@pytest.fixture
def command(session):
    legs = list(
        session.scalars(
            select(FlightLegInstance)
            .where(FlightLegInstance.departure_at > datetime.now(UTC) + timedelta(hours=25))
            .order_by(FlightLegInstance.departure_at)
        )
    )
    assert legs
    connected: dict[str, list[FlightLegInstance]] = {}
    for leg in legs:
        connected.setdefault(leg.flight_instance_id, []).append(leg)
    two_leg_journey = next(
        tuple(item.id for item in sorted(group, key=lambda item: item.sequence))
        for group in connected.values()
        if len(group) == 2 and group[0].destination == group[1].origin
    )

    def build(key="k", two=False, agency=False):
        chosen = two_leg_journey if two else (legs[0].id,)
        return CreateReservation(
            actor_id="agent" if agency else "guest",
            channel=Channel.AGENCY if agency else Channel.DIRECT,
            idempotency_key=key,
            leg_ids=chosen,
            cabin=Cabin.ECONOMY,
            passengers=(PassengerInput("Ada", "Lovelace"),),
            agency_id="agency-1" if agency else None,
            agent_id="agent-7" if agency else None,
            correlation_id="test",
        )

    return build
