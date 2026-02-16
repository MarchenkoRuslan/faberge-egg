import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, lots, order
from app.config import settings
from app.db_init import init_db, seed_first_lot
from app.models import get_db
from app.webhooks import paykilla_callback, stripe_webhook

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("app.startup")


def _is_railway_runtime() -> bool:
    return any(
        os.getenv(env_name)
        for env_name in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_ENVIRONMENT_NAME",
            "RAILWAY_PUBLIC_DOMAIN",
        )
    )


def _validate_database_url_for_runtime(database_url: str) -> None:
    parsed = urlparse(database_url)
    scheme = parsed.scheme
    host = parsed.hostname
    port = parsed.port
    db_name = parsed.path.lstrip("/")
    postgres_schemes = {"postgres", "postgresql", "postgresql+psycopg"}

    if not scheme:
        raise RuntimeError("DATABASE_URL is missing URL scheme (expected postgresql:// or postgresql+psycopg://).")
    if scheme == "sqlite":
        return
    if scheme not in postgres_schemes:
        raise RuntimeError(
            f"DATABASE_URL has unsupported scheme '{scheme}' "
            "(expected postgresql:// or postgresql+psycopg://)."
        )
    if not host:
        raise RuntimeError("DATABASE_URL is missing host.")
    if not db_name:
        raise RuntimeError("DATABASE_URL is missing database name in path.")
    if _is_railway_runtime() and host in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            "Invalid DATABASE_URL for Railway runtime: host is localhost/127.0.0.1 "
            f"(host={host}, port={port or '<missing>'}, database={db_name}). "
            "Use Railway Postgres reference, e.g. DATABASE_URL=${{Postgres.DATABASE_URL}}."
        )


def _db_url_diagnostics(database_url: str) -> str:
    parsed = urlparse(database_url)
    host = parsed.hostname or "<missing>"
    port = parsed.port or "<missing>"
    db_name = parsed.path.lstrip("/") or "<missing>"
    scheme = parsed.scheme or "<missing>"
    query = parsed.query or "<empty>"

    tips = []
    if host in {"localhost", "127.0.0.1"}:
        tips.append("Host points to localhost; in Railway use Postgres service reference in DATABASE_URL.")
    if scheme in {"postgres", "postgresql"}:
        tips.append("URL scheme is fine; app normalizes it to postgresql+psycopg internally.")
    if "sslmode" not in query:
        tips.append("No sslmode in URL query; external managed DBs often require sslmode=require.")
    if not tips:
        tips.append("URL structure looks valid; check network access, DB credentials, and DB service status.")

    return (
        f"scheme={scheme}, host={host}, port={port}, database={db_name}, query={query}; "
        f"tips={' | '.join(tips)}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = settings.DATABASE_URL
    logger.info("Application startup initiated.")
    logger.info("DATABASE_URL diagnostics at startup: %s", _db_url_diagnostics(database_url))
    try:
        _validate_database_url_for_runtime(database_url)
        init_db()
    except Exception as exc:
        logger.exception(
            "Database initialization failed: %s. DATABASE_URL diagnostics: %s",
            str(exc),
            _db_url_diagnostics(database_url),
        )
        raise
    db = next(get_db())
    try:
        seed_first_lot(db)
    finally:
        db.close()
    logger.info("Application startup completed successfully.")
    yield


app = FastAPI(
    title="Marketplace API",
    description=(
        "Backend API for fractional marketplace (lots, orders, Stripe/PayKilla). "
        "Use **Authorize** with the token from `POST /api/auth/login` for protected endpoints (Orders)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Auth", "description": "Register and login (JWT)."},
        {"name": "Lots", "description": "List and get lots (fractions, prices)."},
        {"name": "Orders", "description": "Create order and list my orders (requires auth)."},
        {"name": "Webhooks", "description": "Called by Stripe and PayKilla."},
    ],
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {})["securitySchemes"] = {
        **openapi_schema.get("components", {}).get("securitySchemes", {}),
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT from POST /api/auth/login",
        },
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(lots.router, prefix="/api/lots", tags=["Lots"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
app.include_router(stripe_webhook.router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(paykilla_callback.router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/")
def root():
    return {"status": "ok", "service": "Marketplace API"}


@app.get("/health")
def health():
    return {"status": "ok"}
