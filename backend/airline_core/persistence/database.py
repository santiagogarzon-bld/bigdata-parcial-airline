import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL", "postgresql+psycopg://airline:airline_local_only@localhost:54329/airline"
    )


engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
