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


def _is_localhost(host: str | None) -> bool:
    return host in {"localhost", "127.0.0.1"}


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1].strip()
    return stripped


def _normalize_http_url_for_railway(value: str, is_railway: bool) -> tuple[str, bool]:
    cleaned = _strip_wrapping_quotes(value)
    if not is_railway:
        return cleaned, False
    if _is_http_url(cleaned):
        return cleaned, False

    candidate = urlparse(f"//{cleaned}")
    if candidate.hostname:
        return f"https://{cleaned}", True
    return cleaned, False


def _get_effective_cors_origins(cors_raw: str, is_railway: bool) -> tuple[list[str], list[str]]:
    origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
    normalized_origins: list[str] = []
    coerced_origins: list[str] = []

    for origin in origins:
        normalized, coerced = _normalize_http_url_for_railway(origin, is_railway)
        normalized_origins.append(normalized)
        if coerced:
            coerced_origins.append(origin)

    return normalized_origins, coerced_origins


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
    if _is_railway_runtime() and _is_localhost(host):
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
    if _is_localhost(host):
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


def _validate_required_env_for_runtime() -> None:
    errors = []
    warnings = []
    is_railway = _is_railway_runtime()

    jwt_secret = settings.JWT_SECRET.strip()
    if not jwt_secret:
        errors.append("JWT_SECRET is required.")
    elif is_railway and jwt_secret == "change-me-in-production":
        errors.append(
            "JWT_SECRET uses insecure default value in Railway runtime. "
            "Set JWT_SECRET in Railway Variables."
        )

    base_url, coerced_base = _normalize_http_url_for_railway(settings.BASE_URL, is_railway)
    if coerced_base:
        warnings.append(
            "BASE_URL has no scheme in Railway runtime and was normalized to https:// at startup."
        )
    parsed_base = urlparse(base_url)
    if not _is_http_url(base_url):
        errors.append("BASE_URL must be an absolute http(s) URL, e.g. https://your-app.up.railway.app")
    elif is_railway and _is_localhost(parsed_base.hostname):
        errors.append(
            "BASE_URL points to localhost in Railway runtime. "
            "Set BASE_URL to your public Railway domain."
        )

    cors_raw = settings.CORS_ORIGINS.strip()
    origins, coerced_origins = _get_effective_cors_origins(cors_raw, is_railway)
    if not origins:
        errors.append("CORS_ORIGINS must contain at least one comma-separated origin URL.")
    else:
        invalid_origins = [origin for origin in origins if not _is_http_url(origin)]
        if invalid_origins:
            errors.append(f"CORS_ORIGINS contains invalid URL(s): {', '.join(invalid_origins)}")
        if coerced_origins:
            warnings.append(
                "CORS_ORIGINS includes entries without scheme in Railway runtime and they were "
                f"normalized to https://: {', '.join(coerced_origins)}"
            )

        if is_railway:
            localhost_origins = [
                origin for origin in origins if _is_localhost(urlparse(origin).hostname)
            ]
            if localhost_origins:
                warnings.append(
                    "CORS_ORIGINS includes localhost in Railway runtime: "
                    f"{', '.join(localhost_origins)}"
                )

    if warnings:
        logger.warning("Startup environment warnings: %s", " | ".join(warnings))

    if errors:
        raise RuntimeError("Startup environment validation failed: " + " | ".join(errors))


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = "<unavailable>"
    logger.info("Application startup initiated.")
    try:
        database_url = settings.DATABASE_URL
        logger.info("DATABASE_URL diagnostics at startup: %s", _db_url_diagnostics(database_url))
        _validate_database_url_for_runtime(database_url)
        _validate_required_env_for_runtime()
        init_db()
    except Exception as exc:
        diagnostics = (
            _db_url_diagnostics(database_url)
            if database_url != "<unavailable>"
            else "DATABASE_URL unavailable (missing or unreadable)."
        )
        logger.exception(
            "Database initialization failed: %s. DATABASE_URL diagnostics: %s",
            str(exc),
            diagnostics,
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
    allow_origins=_get_effective_cors_origins(settings.CORS_ORIGINS, _is_railway_runtime())[0],
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
