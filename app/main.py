import logging
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = next(get_db())
    try:
        seed_first_lot(db)
    finally:
        db.close()
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


@app.get("/health")
def health():
    return {"status": "ok"}
