from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import status
from jose import jwt

from app.config import settings
from app.models.user import User


def _register_payload(email: str = "newuser@example.com", display_name: str = "New User") -> dict:
    return {
        "displayName": display_name,
        "email": email,
        "password": "password123",
        "confirmPassword": "password123",
        "termsAgree": True,
    }


def test_register_success(client, db):
    with patch("app.api.auth.send_verify_email") as mock_send:
        response = client.post("/api/auth/register", json=_register_payload())

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "id" in data
    assert data["email"] == "newuser@example.com"
    assert data["displayName"] == "New User"
    assert data["isEmailVerified"] is False
    assert data["requiresEmailVerification"] is True
    mock_send.assert_called_once()

    user = db.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.display_name == "New User"
    assert user.is_email_verified is False
    assert user.terms_accepted_at is not None


def test_register_duplicate_email(client, test_user):
    response = client.post("/api/auth/register", json=_register_payload(email=test_user.email))
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already registered" in response.json()["detail"].lower()


def test_register_password_too_short(client):
    payload = _register_payload()
    payload["password"] = "short"
    payload["confirmPassword"] = "short"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_password_confirmation_mismatch(client):
    payload = _register_payload()
    payload["confirmPassword"] = "different123"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_requires_terms_agree(client):
    payload = _register_payload()
    payload["termsAgree"] = False
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_invalid_email(client):
    payload = _register_payload()
    payload["email"] = "not-an-email"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_password_hash(client, db):
    password = "password123"
    payload = _register_payload(email="hashuser@example.com")
    payload["password"] = password
    payload["confirmPassword"] = password
    with patch("app.api.auth.send_verify_email"):
        response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_200_OK

    user = db.query(User).filter(User.email == "hashuser@example.com").first()
    assert user is not None
    assert user.hashed_password != password
    assert len(user.hashed_password) > 50


def test_login_success(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["expiresIn"], int)
    assert isinstance(data["refreshExpiresIn"], int)
    assert data["expiresIn"] > 0
    assert data["refreshExpiresIn"] > 0


def test_login_unverified_email_blocked(client, db):
    from app.api.auth import get_password_hash

    user = User(
        email="blocked@example.com",
        display_name="Blocked User",
        hashed_password=get_password_hash("testpassword123"),
        is_email_verified=False,
        terms_accepted_at=datetime.now(timezone.utc),
        terms_accepted_ip="127.0.0.1",
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "blocked@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "verified" in response.json()["detail"].lower()


def test_login_wrong_email(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "wrong@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_token_format(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["accessToken"]
    assert len(token.split(".")) == 3


def test_login_token_valid(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["accessToken"]
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(test_user.id)
    assert payload["type"] == "access"
    assert "exp" in payload


def test_login_expires_in(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["expiresIn"] == settings.JWT_EXPIRE_MINUTES * 60


def test_refresh_success_rotates_token(client, test_user):
    login = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert login.status_code == status.HTTP_200_OK
    old_refresh = login.json()["refreshToken"]

    refreshed = client.post("/api/auth/refresh", json={"refreshToken": old_refresh})
    assert refreshed.status_code == status.HTTP_200_OK
    new_refresh = refreshed.json()["refreshToken"]
    assert new_refresh != old_refresh

    reused = client.post("/api/auth/refresh", json={"refreshToken": old_refresh})
    assert reused.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_revokes_refresh_token(client, test_user):
    login = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    refresh_token = login.json()["refreshToken"]

    logout = client.post("/api/auth/logout", json={"refreshToken": refresh_token})
    assert logout.status_code == status.HTTP_200_OK

    reused = client.post("/api/auth/refresh", json={"refreshToken": refresh_token})
    assert reused.status_code == status.HTTP_401_UNAUTHORIZED


def test_verify_email_confirm_success(client):
    with patch("app.api.auth.send_verify_email") as mock_send:
        register = client.post("/api/auth/register", json=_register_payload(email="verifyme@example.com"))
    assert register.status_code == status.HTTP_200_OK
    token = mock_send.call_args.args[2]

    confirm = client.post("/api/auth/verify-email/confirm", json={"token": token})
    assert confirm.status_code == status.HTTP_200_OK

    login = client.post(
        "/api/auth/login",
        json={"email": "verifyme@example.com", "password": "password123"},
    )
    assert login.status_code == status.HTTP_200_OK


def test_verify_email_request_rate_limit(client):
    with patch("app.api.auth.send_verify_email"):
        register = client.post("/api/auth/register", json=_register_payload(email="resend@example.com"))
    assert register.status_code == status.HTTP_200_OK

    resend = client.post("/api/auth/verify-email/request", json={"email": "resend@example.com"})
    assert resend.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_password_reset_flow(client, test_user):
    with patch("app.api.auth.send_password_reset_email") as mock_send:
        forgot = client.post("/api/auth/password/forgot", json={"email": "test@example.com"})
    assert forgot.status_code == status.HTTP_200_OK
    reset_token = mock_send.call_args.args[2]

    reset = client.post(
        "/api/auth/password/reset",
        json={
            "token": reset_token,
            "password": "newpassword123",
            "confirmPassword": "newpassword123",
        },
    )
    assert reset.status_code == status.HTTP_200_OK

    old_login = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert old_login.status_code == status.HTTP_401_UNAUTHORIZED

    new_login = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "newpassword123"},
    )
    assert new_login.status_code == status.HTTP_200_OK


def test_password_forgot_nonexistent_user_is_generic(client):
    with patch("app.api.auth.send_password_reset_email") as mock_send:
        response = client.post("/api/auth/password/forgot", json={"email": "nobody@example.com"})
    assert response.status_code == status.HTTP_200_OK
    mock_send.assert_not_called()


def test_me_returns_current_user_profile(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["displayName"] == "Test User"
    assert data["isEmailVerified"] is True
    assert "createdAt" in data


def test_me_requires_authentication(client):
    response = client.get("/api/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
