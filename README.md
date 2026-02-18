# Marketplace Backend (Python / FastAPI)

REST API for a fractional marketplace with JWT auth, lots, orders, Stripe checkout, and PayKilla callbacks.

## Features

- JWT authentication with access + refresh tokens
- Email verification and password reset by email
- Current user profile endpoint (`/api/auth/me`)
- Public lots API (`/api/lots`, `/api/lots/{id}`)
- Authenticated orders API (`/api/orders`, `/api/orders/me`, `/api/orders/{id}/status`)
- Payment methods endpoint (`/api/orders/payment-methods`)
- Stripe checkout + webhook
- PayKilla callback processing
- Health endpoint (`/health`)

## Project Layout

- `app/main.py` - FastAPI app setup and router registration
- `app/api/` - auth, lots, and orders endpoints
- `app/webhooks/` - Stripe and PayKilla webhook handlers
- `app/services/` - payment and auth helpers
- `app/models/` - SQLAlchemy models and DB wiring
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

Create `.env` in repository root (you can copy from `.env.example`).

```env
# REQUIRED (app startup fails without this)
DATABASE_URL=postgresql://user:password@localhost:5432/marketplace

# REQUIRED IN PRODUCTION (default is insecure)
JWT_SECRET=change-me-in-production

# REQUIRED FOR EMAIL FLOWS (register verification + password reset)
SMTP_HOST=
SMTP_FROM_EMAIL=

# OPTIONAL: auth token settings
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
JWT_REFRESH_EXPIRE_DAYS=30
EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES=1440
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30
EMAIL_RESEND_COOLDOWN_SECONDS=60

# OPTIONAL: frontend links used in emails
FRONTEND_URL=http://localhost:3000
EMAIL_VERIFY_PATH=/verify-email
PASSWORD_RESET_PATH=/restore-password

# OPTIONAL: SMTP details
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_NAME=Marketplace API
SMTP_USE_TLS=true

# OPTIONAL: Stripe (required only if Stripe payments are enabled)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_SUCCESS_URL=http://localhost:3000/success
STRIPE_CANCEL_URL=http://localhost:3000/cancel

# OPTIONAL: PayKilla (required only if PayKilla payments are enabled)
PAYKILLA_API_KEY=
PAYKILLA_WEBHOOK_SECRET=
PAYKILLA_SUCCESS_URL=http://localhost:3000/success
PAYKILLA_CANCEL_URL=http://localhost:3000/cancel

# OPTIONAL: app behavior/runtime
MIN_FRACTIONS=1
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
BASE_URL=http://localhost:8000
DB_CONNECT_RETRIES=10
DB_CONNECT_RETRY_DELAY_SECONDS=1
```

## Migrations

Alembic migrations are applied automatically on app startup for all runtimes.

Manual commands:

```bash
alembic upgrade head
alembic revision -m "describe change"
```

## Deploy to Railway

1. Create a Railway project and connect this repository.
2. Add a PostgreSQL service.
3. Configure app variables:
   - Required: `DATABASE_URL` (use Railway Postgres reference), `JWT_SECRET`
   - Recommended for deployment: `BASE_URL`, `CORS_ORIGINS`
   - Required for email auth flows: `SMTP_HOST`, `SMTP_FROM_EMAIL`
   - Optional: payment provider vars (Stripe/PayKilla) only when those methods are enabled.
4. Configure provider webhooks:
   - Stripe: `https://<railway-domain>/webhooks/stripe`
   - PayKilla: `https://<railway-domain>/webhooks/paykilla`

## API Docs

- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

For protected endpoints, use `accessToken` from `POST /api/auth/login`.

## Running Tests

```bash
pytest -q
```
