import pytest
from fastapi import status
from jose import jwt

from app.config import settings
from app.models.user import User


def test_register_success(client, db):
    """Test successful user registration."""
    response = client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "password123"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "id" in data
    assert data["email"] == "newuser@example.com"
    
    # Verify user was created in database
    user = db.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.email == "newuser@example.com"


def test_register_duplicate_email(client, test_user):
    """Test registration with existing email."""
    response = client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already registered" in response.json()["detail"].lower()


def test_register_password_too_short(client):
    """Test registration with password less than 8 characters."""
    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "short"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    errors = response.json()["detail"]
    assert any("8 characters" in str(error).lower() for error in errors)


def test_register_invalid_email(client):
    """Test registration with invalid email format."""
    response = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_password_hash(client, db):
    """Test that password is hashed, not stored in plain text."""
    password = "password123"
    response = client.post(
        "/api/auth/register",
        json={"email": "hashuser@example.com", "password": password},
    )
    assert response.status_code == status.HTTP_200_OK
    
    user = db.query(User).filter(User.email == "hashuser@example.com").first()
    assert user is not None
    assert user.hashed_password != password
    assert len(user.hashed_password) > 50  # bcrypt hash is long


def test_login_success(client, test_user):
    """Test successful login."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] > 0


def test_login_wrong_email(client, test_user):
    """Test login with wrong email."""
    response = client.post(
        "/api/auth/login",
        json={"email": "wrong@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


def test_login_wrong_password(client, test_user):
    """Test login with wrong password."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


def test_login_token_format(client, test_user):
    """Test that JWT token has correct format."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    
    # JWT tokens have 3 parts separated by dots
    parts = token.split(".")
    assert len(parts) == 3


def test_login_token_valid(client, test_user):
    """Test that JWT token can be decoded and contains correct data."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    
    # Decode token
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert "sub" in payload
    assert payload["sub"] == test_user.id
    assert "exp" in payload


def test_login_expires_in(client, test_user):
    """Test that expires_in matches JWT_EXPIRE_MINUTES."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == status.HTTP_200_OK
    expires_in = response.json()["expires_in"]
    expected_seconds = settings.JWT_EXPIRE_MINUTES * 60
    assert expires_in == expected_seconds
