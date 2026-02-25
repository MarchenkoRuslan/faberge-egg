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
- Showrooms/assets/media:
  - `app/api/showrooms.py`
  - `app/api/assets.py`
  - `app/models/showroom.py`
  - `app/models/asset.py`
  - `app/models/asset_media.py`
  - `app/schemas/showrooms.py`
  - `app/services/storage.py`
  - `tests/test_showrooms.py`
- Assets/orders business flow:
  - `app/api/assets.py`
  - `app/api/order.py`
  - `app/models/asset.py`
  - `app/models/order.py`
  - `app/schemas/showrooms.py`
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
  - Showrooms/assets: `pytest -q tests/test_showrooms.py`
  - Assets/orders: `pytest -q tests/test_lots.py tests/test_orders.py`
  - Payments: `pytest -q tests/test_services.py tests/test_webhooks.py`
- Run full suite for cross-cutting changes: `pytest -q`.

## Known Context to Avoid Re-Learning

- Tests force SQLite in-memory DB via `tests/conftest.py` before app import.
- Startup validation logic lives in `app/main.py` (database URL + required env checks).
- `DATABASE_URL` is mandatory in normal runtime (see `app/config.py`).
- `.env` is not auto-loaded in code; provide environment via process vars or `uvicorn --env-file .env`.
- S3/storage config (`S3_ENDPOINT`, `S3_ACCESS_KEY_ID`, etc.) is optional; storage service degrades gracefully when not configured.
- Seed creates showroom "latvian-treasure", asset "faberge-egg" (with commerce fields), and creates media records with storage keys under `latvian-treasure/faberge-egg/`.
- The `lots` table has been merged into `assets`: all commerce fields (fractions, prices, is_active) now live directly on the Asset model.

