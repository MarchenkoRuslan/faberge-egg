import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.models.database import _normalize_database_url, engine
from app.models import Lot, OneTimeToken, Order, RefreshToken, User  # noqa: F401 - register models

logger = logging.getLogger(__name__)
POSTGRES_MIGRATION_LOCK_KEY = 640_017_451


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
    run_migrations()


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

    normalized_database_url = _normalize_database_url(settings.DATABASE_URL)
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", normalized_database_url)

    logger.info("Running Alembic migrations to head")

    parsed = urlparse(normalized_database_url)
    if parsed.scheme.startswith("postgresql"):
        with engine.connect() as connection:
            logger.info(
                "Acquiring Postgres advisory lock for migrations (key=%s)",
                POSTGRES_MIGRATION_LOCK_KEY,
            )
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": POSTGRES_MIGRATION_LOCK_KEY},
            )
            try:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            finally:
                config.attributes.pop("connection", None)
                if connection.in_transaction():
                    connection.rollback()
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": POSTGRES_MIGRATION_LOCK_KEY},
                    )
                    logger.info("Released Postgres advisory lock for migrations")
                except Exception:
                    logger.warning(
                        "Failed to release Postgres advisory lock cleanly; "
                        "it will be released when the DB connection closes.",
                        exc_info=True,
                    )
    else:
        command.upgrade(config, "head")

    logger.info("Alembic migrations applied successfully")


def seed_first_lot(db_session) -> bool:
    """Insert the first lot if it does not exist.

    Returns True when the lot is inserted, False when it already exists.
    Handles concurrent inserts safely during parallel application startups.
    """
    if db_session.query(Lot).filter(Lot.slug == "faberge-egg").first():
        logger.info("Initial lot already exists; skipping seed")
        return False

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
    try:
        db_session.commit()
        logger.info("Initial lot seeded successfully")
        return True
    except IntegrityError:
        db_session.rollback()
        # A parallel startup may have inserted the same unique slug moments earlier.
        if db_session.query(Lot).filter(Lot.slug == "faberge-egg").first():
            logger.info("Initial lot was inserted by another startup instance; continuing")
            return False
        raise
    except Exception:
        db_session.rollback()
        raise
