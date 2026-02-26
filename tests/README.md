# Backend test guide

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run tests

### Full suite
```bash
pytest -q
```

### Verbose output
```bash
pytest -v
```

### With coverage report
```bash
pytest --cov=app --cov-report=html -q
```

Open `htmlcov/index.html` in your browser to inspect coverage details.

### Single test file
```bash
pytest tests/test_auth.py -q
```

### Single test case
```bash
pytest tests/test_auth.py::test_register_success -q
```

### Fast subset (exclude integration tests)
```bash
pytest -k "not integration" -q
```

## Test structure

- `test_auth.py` - Auth (register, login, JWT, verify, password reset)
- `test_blockchain_service.py` - Blockchain service
- `test_database.py` - DB init, migrations, seed, db_tasks
- `test_dependencies.py` - Auth dependency tests
- `test_email_service.py` - Resend email service
- `test_health.py` - Health endpoint
- `test_integration.py` - End-to-end integration flow
- `test_lots.py` - Assets API (fractions, remaining_special_fractions)
- `test_orders.py` - Orders endpoints
- `test_provenance.py` - Fraction transfer provenance
- `test_services.py` - Payment / service-layer tests with mocks
- `test_showrooms.py` - Showrooms and assets catalog API
- `test_startup_config.py` - Startup validation
- `test_upsale_campaigns.py` - Upsale campaign state machine and admin API
- `test_wallet_service.py` - Wallet service
- `test_webhooks.py` - Stripe and PayKilla webhooks

## Fixtures (conftest.py)

- `client` - FastAPI TestClient
- `db` - Test database (in-memory SQLite)
- `test_user` - Primary test user (admin)
- `test_user2` - Secondary test user
- `test_user_non_admin` - User without admin privileges
- `test_showroom` - Test showroom
- `test_asset` - Active test asset
- `test_asset_inactive` - Inactive test asset
- `test_wallet`, `test_wallet2` - Blockchain wallets
- `test_fraction_transfer` - Sample fraction transfer
- `auth_token` - JWT for test user
- `auth_headers` - Authorization headers

## Notes

- Tests use isolated in-memory SQLite (no PostgreSQL required).
- External services (Stripe, PayKilla, Resend) are mocked.
- Each test runs in an isolated DB transaction.
