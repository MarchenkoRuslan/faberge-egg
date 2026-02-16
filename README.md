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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Optional environment variables

Create `.env` in the repository root to override defaults:

```env
DATABASE_URL=sqlite:///./marketplace.db
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
```

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
