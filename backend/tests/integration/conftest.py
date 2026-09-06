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
    legs = list(session.scalars(select(FlightLegInstance).order_by(FlightLegInstance.departure_at)))

    def build(key="k", two=False, agency=False):
        chosen = (legs[1].id, legs[2].id) if two else (legs[0].id,)
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
