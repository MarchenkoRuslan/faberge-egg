from unittest.mock import MagicMock

from fastapi import status


def test_root_returns_ok(client):
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Marketplace API"


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


def test_health_returns_503_when_db_unavailable(client):
    """Health check must return 503 when database is unavailable (for load balancers)."""
    from app.main import app
    from app.core.database import get_db

    broken_session = MagicMock()
    broken_session.execute.side_effect = Exception("connection refused")

    def override_get_db():
        yield broken_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json() == {"status": "error", "database": "unavailable"}
    finally:
        app.dependency_overrides.pop(get_db, None)
