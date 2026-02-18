import logging
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.models.database import Base, _normalize_database_url, engine
from app.models import Lot, OneTimeToken, Order, RefreshToken, User  # noqa: F401 - register models

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
    if settings.DATABASE_URL.startswith("sqlite://"):
        Base.metadata.create_all(bind=engine)
        return

    run_migrations()
    Base.metadata.create_all(bind=engine)


def run_migrations() -> None:
    """Apply Alembic migrations to the latest revision."""
    try:
        from alembic import command
        from alembic.config import Config
    except Exception as exc:  # pragma: no cover - environment/setup failure
        raise RuntimeError(
            "Alembic is required for non-sqlite runtime. Install dependencies from requirements.txt."
        ) from exc

    project_root = Path(__file__).resolve().parent.parent
    alembic_ini = project_root / "alembic.ini"
    script_location = project_root / "alembic"
    if not alembic_ini.exists() or not script_location.exists():
        raise RuntimeError("Alembic configuration is missing (alembic.ini or alembic/ directory not found).")

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", _normalize_database_url(settings.DATABASE_URL))
    command.upgrade(config, "head")


def seed_first_lot(db_session):
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
