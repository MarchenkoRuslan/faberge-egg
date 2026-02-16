import os
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.models.database import Base, get_db
from app.models.lot import Lot
from app.models.user import User

# Override settings for tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_mock"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_mock"
os.environ["PAYKILLA_API_KEY"] = "pk_test_mock"
os.environ["PAYKILLA_WEBHOOK_SECRET"] = "pk_whsec_test_mock"

# Create test database engine
test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=test_engine)
    db_session = TestSessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database override."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user."""
    from app.api.auth import get_password_hash

    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user2(db: Session) -> User:
    """Create a second test user."""
    from app.api.auth import get_password_hash

    user = User(
        email="test2@example.com",
        hashed_password=get_password_hash("testpassword123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_lot(db: Session) -> Lot:
    """Create a test lot."""
    lot = Lot(
        name="Test Lot",
        slug="test-lot",
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=Decimal("0.03"),
        price_nominal_eur=Decimal("0.09"),
        sold_special_fractions=0,
        is_active=True,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@pytest.fixture
def test_lot_inactive(db: Session) -> Lot:
    """Create an inactive test lot."""
    lot = Lot(
        name="Inactive Lot",
        slug="inactive-lot",
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=Decimal("0.03"),
        price_nominal_eur=Decimal("0.09"),
        sold_special_fractions=0,
        is_active=False,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@pytest.fixture
def auth_token(client: TestClient, test_user: User) -> str:
    """Get auth token for test user."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Get auth headers with token."""
    return {"Authorization": f"Bearer {auth_token}"}
