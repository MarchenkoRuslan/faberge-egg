# Agent Working Notes for `faberge-egg`

## Goal

Move fast with minimal codebase scanning. Start from known entrypoints, then expand only when needed.

## Code-First Discipline

- **Read before write.** Before changing code, read the relevant files fully. Understand existing patterns, naming, error handling, and structure.
- **Build on what exists.** Reuse existing utilities, schemas, and conventions. Do not introduce new patterns where project patterns already exist.
- **Preserve consistency.** Match indentation, docstrings style, import order, and error handling of surrounding code.
- **Minimal diff.** Change only what is necessary. Avoid refactoring unrelated code unless explicitly requested.

## Documentation & Libraries

- **Check docs for external APIs.** For FastAPI, SQLAlchemy, Stripe, Pydantic, etc., use Context7 MCP to fetch up-to-date documentation. Do not guess API signatures or behavior.
- **Verify before implementing.** If unsure about a library feature, fetch the docs first. Prefer official docs over assumptions.

## Senior-Level Practices

- **Explicit error handling.** No bare `except:` or `except Exception:` without re-raise or logging. Use specific exceptions, log context, and preserve stack traces where appropriate.
- **Defensive coding.** Validate inputs (Pydantic, path params), handle edge cases (empty lists, None), and avoid implicit assumptions.
- **Logging.** Use structured logging for diagnostics; avoid `print()` for production paths.
- **Security.** Do not hardcode secrets. Validate webhook signatures (Stripe, PayKilla). Sanitize user input before DB/storage.
- **Tests.** Add or update tests for changed behavior. Prefer existing test patterns (conftest fixtures, parametrize).

## Project Snapshot

- Stack: FastAPI + SQLAlchemy + JWT auth + Stripe/PayKilla integrations.
- App entrypoint: `app/main.py`.
- Settings/env: `app/core/config.py`.
- DB init/seed: `app/db_init.py`.
- CI: `.github/workflows/python-package.yml` (Python 3.11, `flake8`, `pytest -q`).
- Architecture: domain-oriented. Core: `app/core/`. Domains: `app/domains/`. Shared: `app/shared/`. Models: `app/models/`. Removed: `app/api`, `app/webhooks`, `app/schemas`, `app/utils`, `app/services`, `scripts`.

## Read-First Map (By Task Type)

- Startup/env/runtime validation:
  - `app/core/config.py`
  - `app/main.py`
  - `tests/test_startup_config.py`
- Auth/JWT/dependencies:
  - `app/domains/auth/` (router, service, schemas)
  - `app/core/dependencies.py`
  - `app/models/user.py`
  - `tests/test_auth.py`
  - `tests/test_dependencies.py`
- Catalog (showrooms/assets):
  - `app/domains/catalog/` (router, service, schemas)
  - `app/models/showroom.py`, `app/models/asset.py`, `app/models/asset_media.py`
  - `app/shared/storage.py`
  - `tests/test_showrooms.py`
  - `tests/test_lots.py`
- Orders:
  - `app/domains/orders/` (router, service, schemas)
  - `app/models/order.py`
  - `tests/test_orders.py`
- Provenance:
  - `app/domains/provenance/` (router, service, schemas)
  - `tests/test_provenance.py`
- Payments/webhooks:
  - `app/domains/payments/` (stripe_service, paykilla_service, payment_gateways, payment_settlement)
  - `app/domains/payments/routers/` (stripe_webhook, paykilla_callback)
  - `tests/test_services.py`
  - `tests/test_webhooks.py`
- Upsale campaigns (post-purchase email marketing):
  - `app/models/upsale_campaign.py`
  - `app/domains/campaigns/` (router, schemas, service)
  - `app/shared/email_service.py` (send_upsale_email)
  - `app/domains/payments/payment_settlement.py` (_trigger_upsale_campaign)
  - `app/domains/campaigns/` (router, schemas)
  - `tests/test_upsale_campaigns.py`
- DB/session wiring:
  - `app/core/database.py`
  - `app/models/database.py` (re-exports from core)
  - `tests/conftest.py`
  - `tests/test_database.py`

## Search Policy (Do This Before Global Scans)

- Do not scan the whole repository first.
- Start with the read-first map above for the relevant domain. Domains live under `app/domains/<domain>/`.
- Use targeted symbol search (`rg "<symbol_or_function_name>" app tests`) only if needed.
- Expand to other files only when:
  - a referenced symbol is unresolved, or
  - tests indicate behavior outside the current domain.

## Test-First Validation Policy

- Run the smallest relevant test slice before full suite:
  - Startup/env: `pytest -q tests/test_startup_config.py`
  - Auth: `pytest -q tests/test_auth.py tests/test_dependencies.py`
  - Showrooms/assets: `pytest -q tests/test_showrooms.py`
  - Assets/orders: `pytest -q tests/test_lots.py tests/test_orders.py`
  - Payments: `pytest -q tests/test_services.py tests/test_webhooks.py`
  - Upsale campaigns: `pytest -q tests/test_upsale_campaigns.py`
- Run full suite for cross-cutting changes: `pytest -q`.

## Known Context to Avoid Re-Learning

- Tests force SQLite in-memory DB via `tests/conftest.py` before app import.
- Startup validation logic lives in `app/main.py` (database URL + required env checks).
- `DATABASE_URL` is mandatory in normal runtime (see `app/core/config.py`).
- `.env` is not auto-loaded in code; provide environment via process vars or `uvicorn --env-file .env`.
- S3/storage config (`S3_ENDPOINT`, `S3_ACCESS_KEY_ID`, etc.) is optional; storage service degrades gracefully when not configured.
- Seed creates showroom "latvian-treasure", asset "faberge-egg" (with commerce fields), and creates media records with storage keys under `latvian-treasure/faberge-egg/`.
- The `lots` table has been merged into `assets`: all commerce fields (fractions, prices, is_active) now live directly on the Asset model.
- **Upsale campaigns**: post-purchase email marketing funnel (4d→upsale1→7d check→upsale2/bonus→upsale3). State machine in `app/domains/campaigns/service.py`. Background asyncio-task in `lifespan()` processes due campaigns every N seconds. Triggered from `app/domains/payments/payment_settlement.py` (`settle_order_payment`). Gated by `UPSALE_CAMPAIGN_ENABLED` (default: False). Requires Resend template IDs: `RESEND_TEMPLATE_UPSALE1`, `_UPSALE2`, `_UPSALE3`, `_BONUS_UPSALE`. Admin API at `/api/admin/campaigns`. Tables: `upsale_campaigns`, `campaign_email_logs`.

## Cursor Cloud specific instructions

### Prerequisites (already installed by VM snapshot)

- Python 3.12 with `~/.local/bin` on `PATH`
- PostgreSQL 16 (local, started via `sudo pg_ctlcluster 16 main start`)
- All pip packages from `requirements.txt` + `flake8`

### Running tests

Tests use SQLite via `tests/conftest.py` — no PostgreSQL needed:

```
pytest -q
```

### Lint

```
flake8 app tests --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 app tests --count --exit-zero --statistics
```

### Running the dev server

Alembic migrations require PostgreSQL (SQLite is NOT supported for `ALTER constraints`). Start PostgreSQL first, then launch uvicorn:

```bash
sudo pg_ctlcluster 16 main start
DATABASE_URL="postgresql://ubuntu:devpassword@localhost/marketplace" \
  JWT_SECRET="dev-secret-key" \
  BASE_URL="http://localhost:8000" \
  CORS_ORIGINS="http://localhost:3000" \
  FRONTEND_URL="http://localhost:3000" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app runs migrations and seeds data automatically on startup. Swagger UI is at `http://localhost:8000/docs`.

### Gotchas

- The app uses `pbkdf2_sha256` for password hashing (NOT bcrypt) — see `pwd_context` in `app/domains/auth/service.py`.
- Registration requires Resend email service (`RESEND_API_KEY`). Without it, registration fails. For dev testing, create users directly in the DB or use `tests/conftest.py` fixtures.
- S3, Stripe, PayKilla, and Resend are all optional for local dev — the app starts and core endpoints work without them.
- `~/.local/bin` must be on `PATH` for `uvicorn`, `pytest`, `flake8` commands to work.
