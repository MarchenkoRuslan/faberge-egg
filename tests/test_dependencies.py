from datetime import datetime, timedelta, timezone

from fastapi import status
from jose import jwt

from app.core.config import settings
from app.core.dependencies import get_current_user_optional


def test_get_current_user_success(client, test_user, db):
    """Test successful user retrieval with valid token."""
    token = jwt.encode(
        {"sub": str(test_user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    from fastapi.security import HTTPAuthorizationCredentials

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user_optional(credentials, db)
    assert user is not None
    assert user.id == test_user.id
    assert user.email == test_user.email


def test_get_current_user_no_token(client):
    """Test get_current_user without token."""
    response = client.get("/api/orders/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "authenticated" in response.json()["detail"].lower()


def test_get_current_user_invalid_token(client):
    """Test get_current_user with invalid token."""
    response = client.get(
        "/api/orders/me",
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_expired_token(client, test_user):
    """Test get_current_user with expired token."""
    expired_token = jwt.encode(
        {
            "sub": str(test_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(
        "/api/orders/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_nonexistent_user(client, db):
    """Test get_current_user with token for non-existent user."""
    fake_user_id = 99999
    token = jwt.encode(
        {"sub": str(fake_user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(
        "/api/orders/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_optional_none(client, db):
    """Test get_current_user_optional returns None when no credentials."""
    user = get_current_user_optional(None, db)
    assert user is None


def test_get_current_user_optional_invalid_token(client, db):
    """Test get_current_user_optional returns None for invalid token."""
    from fastapi.security import HTTPAuthorizationCredentials

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="invalid_token",
    )
    user = get_current_user_optional(credentials, db)
    assert user is None


def test_get_current_user_raises_exception(client):
    """Verify via endpoint behavior because dependency injection handles raising."""
    response = client.get("/api/orders/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
