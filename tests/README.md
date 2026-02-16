# Backend test guide

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run tests

### Full suite
```bash
pytest
```

### Verbose output
```bash
pytest -v
```

### With coverage report
```bash
pytest --cov=app --cov-report=html
```

Open `htmlcov/index.html` in your browser to inspect coverage details.

### Single test file
```bash
pytest tests/test_auth.py
```

### Single test case
```bash
pytest tests/test_auth.py::test_register_success
```

### Fast subset (exclude integration tests)
```bash
pytest -k "not integration"
```

## Test structure

- `test_auth.py` - Authentication tests (register, login, JWT)
- `test_lots.py` - Lots endpoints tests
- `test_orders.py` - Orders endpoints tests
- `test_webhooks.py` - Stripe and PayKilla webhook tests
- `test_services.py` - Service-layer tests with mocks
- `test_dependencies.py` - Auth dependency tests
- `test_integration.py` - End-to-end integration flow tests

## Fixtures

- `client` - FastAPI `TestClient`
- `db` - Test database (in-memory SQLite)
- `test_user` - Primary test user
- `test_user2` - Secondary test user
- `test_lot` - Active test lot
- `test_lot_inactive` - Inactive test lot
- `auth_token` - JWT for test user
- `auth_headers` - Authorization headers

## Notes

- Tests run against an isolated in-memory SQLite database.
- External services (Stripe, PayKilla) are mocked.
- Each test is executed in an isolated DB transaction.
