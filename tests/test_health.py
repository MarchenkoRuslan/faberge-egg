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
    assert response.json() == {"status": "ok"}
