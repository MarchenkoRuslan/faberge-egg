import logging
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.models.database import Base, engine
from app.models import User, Lot, Order  # noqa: F401 - register models

logger = logging.getLogger(__name__)


def wait_for_db(retries: int, retry_delay_seconds: int) -> None:
    """Wait for database to accept connections before running migrations."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established on attempt %s", attempt)
            return
        except OperationalError as exc:
            last_error = exc
            logger.warning(
                "Database not reachable yet (attempt %s/%s): %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(retry_delay_seconds)

    raise RuntimeError(
        "Database is unreachable after "
        f"{retries} attempts. Check DATABASE_URL and ensure the DB server is running."
    ) from last_error


def init_db():
    wait_for_db(
        retries=settings.DB_CONNECT_RETRIES,
        retry_delay_seconds=settings.DB_CONNECT_RETRY_DELAY_SECONDS,
    )
    Base.metadata.create_all(bind=engine)


def seed_first_lot(db_session):
    from app.models import Lot

    if db_session.query(Lot).filter(Lot.slug == "faberge-egg").first():
        return
    lot = Lot(
        name="Faberge Egg",
        slug="faberge-egg",
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=0.03,
        price_nominal_eur=0.09,
        sold_special_fractions=0,
        is_active=True,
    )
    db_session.add(lot)
    db_session.commit()
