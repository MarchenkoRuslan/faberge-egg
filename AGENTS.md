# Agent Working Notes for `faberge-egg`

## Goal
Move fast with minimal codebase scanning. Start from known entrypoints, then expand only when needed.

## Project Snapshot
- Stack: FastAPI + SQLAlchemy + JWT auth + Stripe/PayKilla integrations.
- App entrypoint: `app/main.py`.
- Settings/env: `app/config.py`.
- DB init/seed: `app/db_init.py`.
- CI: `.github/workflows/python-package.yml` (Python 3.11, `flake8`, `pytest -q`).

## Read-First Map (By Task Type)
- Startup/env/runtime validation:
  - `app/config.py`
  - `app/main.py`
  - `tests/test_startup_config.py`
- Auth/JWT/dependencies:
  - `app/api/auth.py`
  - `app/dependencies.py`
  - `app/models/user.py`
  - `tests/test_auth.py`
  - `tests/test_dependencies.py`
- Lots/orders business flow:
  - `app/api/lots.py`
  - `app/api/order.py`
  - `app/models/lot.py`
  - `app/models/order.py`
  - `app/schemas/lots.py`
  - `app/schemas/orders.py`
  - `tests/test_lots.py`
  - `tests/test_orders.py`
- Payments/webhooks:
  - `app/services/payment_gateways.py`
  - `app/services/stripe_service.py`
  - `app/services/paykilla_service.py`
  - `app/webhooks/stripe_webhook.py`
  - `app/webhooks/paykilla_callback.py`
  - `tests/test_services.py`
  - `tests/test_webhooks.py`
- DB/session wiring:
  - `app/models/database.py`
  - `tests/conftest.py`
  - `tests/test_database.py`

## Search Policy (Do This Before Global Scans)
- Do not scan the whole repository first.
- Start with the read-first map above for the relevant domain.
- Use targeted symbol search (`rg "<symbol_or_function_name>" app tests`) only if needed.
- Expand to other files only when:
  - a referenced symbol is unresolved, or
  - tests indicate behavior outside the current domain.

## Test-First Validation Policy
- Run the smallest relevant test slice before full suite:
  - Startup/env: `pytest -q tests/test_startup_config.py`
  - Auth: `pytest -q tests/test_auth.py tests/test_dependencies.py`
  - Lots/orders: `pytest -q tests/test_lots.py tests/test_orders.py`
  - Payments: `pytest -q tests/test_services.py tests/test_webhooks.py`
- Run full suite for cross-cutting changes: `pytest -q`.

## Known Context to Avoid Re-Learning
- Tests force SQLite in-memory DB via `tests/conftest.py` before app import.
- Startup validation logic lives in `app/main.py` (database URL + required env checks).
- `DATABASE_URL` is mandatory in normal runtime (see `app/config.py`).
- `.env` is not auto-loaded in code; provide environment via process vars or `uvicorn --env-file .env`.
