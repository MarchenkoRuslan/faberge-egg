# Marketplace Backend (Python / FastAPI)

REST API for a fractional marketplace with JWT auth, lots, orders, Stripe checkout, and PayKilla callbacks.

## Features

- JWT-based authentication (`/api/auth/register`, `/api/auth/login`)
- Public lots API (`/api/lots`, `/api/lots/{id}`)
- Authenticated orders API (`/api/orders`, `/api/orders/me`, `/api/orders/{id}/status`)
- Payment methods discovery endpoint (`/api/orders/payment-methods`)
- Payment integrations:
  - Stripe Checkout session creation
  - Stripe webhook processing
  - PayKilla callback processing
- Healthcheck endpoint (`/health`)

## Project layout

- `app/main.py` — FastAPI app setup and router registration
- `app/api/` — Auth, lots, and orders endpoints
- `app/webhooks/` — Stripe and PayKilla webhook handlers
- `app/services/` — Payment service helpers and gateway registry for extensible provider integrations (including future crypto gateways)
- `app/models/` — SQLAlchemy models and DB wiring
- `tests/` — automated tests

## Local run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

### Environment variables

Create `.env` in the repository root (you can copy from `.env.example`). `DATABASE_URL` is required.
The app does not auto-load `.env` in code, so pass it explicitly via `--env-file .env` (or export vars in your shell):

```env
DATABASE_URL=postgresql://user:password@localhost:5432/marketplace
JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_SUCCESS_URL=http://localhost:3000/success
STRIPE_CANCEL_URL=http://localhost:3000/cancel

PAYKILLA_API_KEY=
PAYKILLA_WEBHOOK_SECRET=
PAYKILLA_SUCCESS_URL=http://localhost:3000/success
PAYKILLA_CANCEL_URL=http://localhost:3000/cancel

MIN_FRACTIONS=1
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
BASE_URL=http://localhost:8000
DB_CONNECT_RETRIES=10
DB_CONNECT_RETRY_DELAY_SECONDS=1
```


## Deploy to Railway

1. Create a new Railway project and connect this repository.
2. Add a **PostgreSQL** service in Railway. Railway injects `DATABASE_URL` for the app service automatically.
3. Set required app variables in Railway:
   - `JWT_SECRET` (must be a strong secret in production)
   - `CORS_ORIGINS` (your frontend domain(s), comma-separated)
   - `BASE_URL` (your Railway public domain, for example `https://your-app.up.railway.app`)
   - Payment variables as needed: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, `PAYKILLA_API_KEY`, `PAYKILLA_WEBHOOK_SECRET`, `PAYKILLA_SUCCESS_URL`, `PAYKILLA_CANCEL_URL`
4. Configure provider webhooks to point to your Railway domain:
   - Stripe: `https://<railway-domain>/webhooks/stripe`
   - PayKilla: `https://<railway-domain>/webhooks/paykilla`
5. Deploy. The included `Procfile` starts Uvicorn using Railway's `PORT` value.

> PostgreSQL is required for all environments. Railway-managed PostgreSQL is recommended for production.

## API docs

- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

For protected endpoints, use **Authorize** in Swagger UI with a bearer token from `POST /api/auth/login`.

## Running tests

```bash
pytest -q
```
