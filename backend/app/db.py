import logging
import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .models import Base

log = logging.getLogger("db")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://iiot:iiot@timescaledb:5432/iiot"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(retries: int = 10, delay_seconds: float = 3):
    # Postgres' healthcheck can report ready a moment before it accepts
    # connections; retry rather than crash the whole container on that race.
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(engine)
            break
        except OperationalError as exc:
            if attempt == retries:
                raise
            log.warning("DB not ready yet (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay_seconds)

    with engine.connect() as conn:
        conn.execute(text("SELECT create_hypertable('readings', 'time', if_not_exists => TRUE);"))
        conn.commit()
