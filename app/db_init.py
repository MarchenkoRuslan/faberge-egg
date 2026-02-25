import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.models.database import SessionLocal, _normalize_database_url, engine
from app.models import (  # noqa: F401 - register models
    Asset, AssetMedia, OneTimeToken, Order, RefreshToken, Showroom, User,
)

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


def _table_exists(table_name: str) -> bool:
    with engine.connect() as connection:
        return inspect(connection).has_table(table_name)


def assets_table_exists() -> bool:
    return _table_exists("assets")


def run_seed(*, require_schema: bool = True) -> bool:
    """Seed initial application data.

    When ``require_schema`` is False, missing tables are treated as a warning so a web
    process can start without running migrations in the same startup lifecycle.
    """
    if not assets_table_exists():
        message = "Cannot seed initial data: 'assets' table is missing. Run migrations first."
        if require_schema:
            raise RuntimeError(message)
        logger.warning("Skipping DB seed on startup because assets table is missing (run migrations first)")
        return False

    showrooms_ready = _table_exists("showrooms")
    if not showrooms_ready and require_schema:
        raise RuntimeError("Cannot seed showroom data: 'showrooms' table is missing. Run migrations first.")
    if not showrooms_ready:
        logger.warning("Skipping showroom seed: 'showrooms' table not yet created (run migrations first)")

    db_session = SessionLocal()
    try:
        showroom_seeded = seed_showroom_and_asset(db_session) if showrooms_ready else False
        return showroom_seeded
    finally:
        db_session.close()


def prepare_database(*, include_seed: bool = True) -> None:
    """Wait for DB, run migrations, and optionally seed initial data."""
    wait_for_db(
        retries=settings.DB_CONNECT_RETRIES,
        retry_delay_seconds=settings.DB_CONNECT_RETRY_DELAY_SECONDS,
    )
    run_migrations()
    if include_seed:
        run_seed(require_schema=True)


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
                if connection.in_transaction():
                    connection.commit()
            except Exception:
                if connection.in_transaction():
                    connection.rollback()
                raise
            finally:
                config.attributes.pop("connection", None)
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


_INITIAL_MEDIA = [
    {
        "kind": "hero",
        "media_type": "image/jpeg",
        "storage_key": "latvian-treasure/faberge-egg/hero.jpg",
        "filename": "hero.jpg",
        "alt_text": "Jeweled Faberge Easter Egg by Mikhail Perkhin",
        "sort_order": 0,
    },
    {
        "kind": "gallery",
        "media_type": "image/jpeg",
        "storage_key": "latvian-treasure/faberge-egg/gallery-1.jpg",
        "filename": "gallery-1.jpg",
        "alt_text": "Faberge Egg detail view",
        "sort_order": 1,
    },
    {
        "kind": "gallery",
        "media_type": "image/jpeg",
        "storage_key": "latvian-treasure/faberge-egg/gallery-2.jpg",
        "filename": "gallery-2.jpg",
        "alt_text": "Faberge Egg close-up",
        "sort_order": 2,
    },
    {
        "kind": "gallery",
        "media_type": "image/jpeg",
        "storage_key": "latvian-treasure/faberge-egg/gallery-3.jpg",
        "filename": "gallery-3.jpg",
        "alt_text": "Faberge Egg side view",
        "sort_order": 3,
    },
    {
        "kind": "gallery",
        "media_type": "image/jpeg",
        "storage_key": "latvian-treasure/faberge-egg/gallery-4.jpg",
        "filename": "gallery-4.jpg",
        "alt_text": "Faberge Egg alternate angle",
        "sort_order": 4,
    },
]


def seed_showroom_and_asset(db_session) -> bool:
    """Create the initial showroom, asset with commerce fields, and media records.

    Idempotent: skips when the showroom already exists.
    """
    if db_session.query(Showroom).filter(Showroom.slug == "latvian-treasure").first():
        logger.info("Showroom 'latvian-treasure' already exists; skipping seed")
        return False

    showroom = Showroom(
        slug="latvian-treasure",
        name="Latvian Faberge Treasure",
        headline="A unique collection of Faberge masterpieces",
        description=(
            "Discover the Latvian Faberge Treasure — an exclusive collection "
            "of imperial Faberge eggs available for fractional ownership."
        ),
        meta={
            "image_key": "latvian-treasure/showroom-image.jpg",
            "background_image_key": "latvian-treasure/showroom-background.jpg",
        },
        status="active",
        sort_order=0,
    )
    db_session.add(showroom)
    try:
        db_session.flush()
    except IntegrityError:
        db_session.rollback()
        logger.info("Showroom 'latvian-treasure' inserted by another instance; continuing")
        return False

    asset = Asset(
        showroom_id=showroom.id,
        slug="faberge-egg",
        name="Jeweled Easter Egg",
        headline="By Faberge firm",
        description=(
            "An authentic jeweled Easter Egg created in the workshop of Carl Faberge "
            "during the firm's golden period and attributed to Mikhail Perkhin, one of "
            "Faberge's leading masters. The piece bears the maker's personal hallmark "
            "and stylistic features characteristic of Perkhin's late 19th century work."
        ),
        meta={
            "maker": "Faberge firm",
            "master": "Mikhail Perkhin",
            "year": "1898",
            "dimensions": "7.5 x 15.1 cm",
            "material": "Gold",
            "origin": "Latvia",
            "period": "Imperial Russia",
            "type": "Decorative Art",
        },
        status="active",
        sort_order=0,
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=0.03,
        price_nominal_eur=0.09,
        sold_special_fractions=0,
        is_active=True,
    )
    db_session.add(asset)
    db_session.flush()

    for media_data in _INITIAL_MEDIA:
        media = AssetMedia(asset_id=asset.id, **media_data)
        db_session.add(media)

    try:
        db_session.commit()
        logger.info("Showroom, asset and media seeded successfully")
    except IntegrityError:
        db_session.rollback()
        logger.info("Showroom seed conflict (parallel startup); continuing")
        return False
    except Exception:
        db_session.rollback()
        raise

    return True
