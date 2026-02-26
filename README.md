# Marketplace Backend (Python / FastAPI)

REST API for a fractional marketplace with JWT auth, showrooms, assets, orders, Stripe checkout, and PayKilla callbacks.

## Features

- JWT authentication with access + refresh tokens
- Email verification and password reset by email
- Current user profile endpoint (`/api/auth/me`)
- Public showrooms API (`/api/showrooms`, `/api/showrooms/{slug}`)
- Public assets API (`/api/assets`, `/api/assets/{slug}`)
- Authenticated orders API (`/api/orders`, `/api/orders/me`, `/api/orders/{id}/status`)
- Payment methods endpoint (`/api/orders/payment-methods`)
- Stripe checkout + webhook
- PayKilla callback processing (requires `PAYKILLA_IMPLEMENTED=true` when implemented)
- Health endpoint (`/health`) with DB connectivity check (returns 503 if DB unavailable)
- Admin API for upsale campaigns (`/api/admin/campaigns`)

## Project Layout

- `app/main.py` - FastAPI app setup
- `app/core/` - config, database, dependencies, rate limiting
- `app/domains/` - auth, catalog (showrooms+assets), orders, provenance, campaigns, payments
- `app/shared/` - storage, email, blockchain, wallet services
- `app/models/` - SQLAlchemy models
- `alembic/` - database migrations
- `tests/` - automated tests

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

## Environment Variables

Copy `.env.example` to `.env` and adjust. See `.env.example` for the full list with descriptions.

## Migrations

By default, the app can run migrations/seed on startup (`RUN_MIGRATIONS_ON_STARTUP=true`,
`RUN_SEED_ON_STARTUP=true`) for local development.

For production (especially Railway), prefer a separate DB prepare step and disable
migrations/seed in the web service startup to avoid readiness timeouts and migration lock contention.

Manual commands:

```bash
alembic upgrade head
alembic revision -m "describe change"
python -m app.db_tasks wait
python -m app.db_tasks migrate
python -m app.db_tasks seed
python -m app.db_tasks prepare
```

## Deploy to Railway

1. Create a Railway project and connect this repository.
2. Add a PostgreSQL service.
3. Configure app variables:
   - Required: `DATABASE_URL` (use Railway Postgres reference), `JWT_SECRET`
   - Recommended for deployment: `BASE_URL`, `CORS_ORIGINS`
   - Required for email auth flows: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_TEMPLATE_VERIFY_EMAIL`, `RESEND_TEMPLATE_PASSWORD_RESET`
   - Resend sender domain must be verified; template variables: verify `CONFIRM_LINK`, `USER_NAME`; reset `RESET_LINK`, `USER_NAME`.
   - Rate limit for email endpoints: `RATE_LIMIT_EMAIL_REQUESTS` (default 5), `RATE_LIMIT_EMAIL_WINDOW_SECONDS` (default 900) — per IP.
   - Optional: `ADMIN_EMAILS` for admin API access.
   - Optional: payment provider vars (Stripe/PayKilla) only when those methods are enabled.
   - If `BLOCKCHAIN_ENABLED=true`, set `WALLET_ENCRYPTION_KEY`.
4. Run DB prepare as a one-off/predeploy step (same `DATABASE_URL` and env vars):
   - `python -m app.db_tasks prepare`
5. Deploy the web service using the normal start command (from `railway.json`).
6. Verify startup:
   - `GET /health` returns `200` with `{"status":"ok","database":"ok"}`; returns `503` if DB unavailable.
   - Logs contain `Application startup completed successfully.`
   - Railway Postgres service logs such as `connection reset by peer`, `invalid length of startup packet`,
     or `pg_stat_statements does not exist` can appear independently of app startup success.
7. Configure provider webhooks:
   - Stripe: `https://<railway-domain>/webhooks/stripe`
   - PayKilla: `https://<railway-domain>/webhooks/paykilla`

## API Docs

- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

For protected endpoints, use `accessToken` from `POST /api/auth/login`. Admin endpoints require a user with `is_admin=true` or email in `ADMIN_EMAILS`.

## Running Tests

```bash
pytest -q
```

Tests use SQLite in-memory DB (no PostgreSQL required). See `tests/conftest.py`.
