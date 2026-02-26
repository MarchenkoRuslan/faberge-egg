import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Override settings for tests before importing app modules.
TEST_DATABASE_URL = "sqlite:///:memory:"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_mock"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_mock"
os.environ["PAYKILLA_API_KEY"] = "pk_test_mock"
os.environ["PAYKILLA_WEBHOOK_SECRET"] = "pk_whsec_test_mock"
os.environ["PAYKILLA_IMPLEMENTED"] = "true"  # Tests use mocked create_payment
# Relax rate limit in tests so email-sending endpoints don't return 429
os.environ["RATE_LIMIT_EMAIL_REQUESTS"] = "1000"
os.environ["RATE_LIMIT_EMAIL_WINDOW_SECONDS"] = "1"
os.environ["WALLET_ENCRYPTION_KEY"] = "uN4BJBTnBE7uXEe0bvq4Zmd6QNbRX6rGqljTTyAW4Is="
os.environ["ADMIN_EMAILS"] = "test@example.com,test2@example.com"

# Create test database engine.
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    from app.core.database import Base

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
    from app.main import app
    from app.core.database import get_db

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    from app.domains.auth.service import get_password_hash
    from app.models.user import User

    user = User(
        email="test@example.com",
        display_name="Test User",
        hashed_password=get_password_hash("testpassword123"),
        is_email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        terms_accepted_at=datetime.now(timezone.utc),
        terms_accepted_ip="127.0.0.1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user_non_admin(db: Session):
    """Create a test user without admin privileges."""
    from app.domains.auth.service import get_password_hash
    from app.models.user import User

    user = User(
        email="nonadmin@example.com",
        display_name="Non Admin",
        hashed_password=get_password_hash("testpassword123"),
        is_email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        terms_accepted_at=datetime.now(timezone.utc),
        terms_accepted_ip="127.0.0.1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user2(db: Session):
    """Create a second test user."""
    from app.domains.auth.service import get_password_hash
    from app.models.user import User

    user = User(
        email="test2@example.com",
        display_name="Test User 2",
        hashed_password=get_password_hash("testpassword123"),
        is_email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        terms_accepted_at=datetime.now(timezone.utc),
        terms_accepted_ip="127.0.0.1",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_showroom(db: Session):
    """Create a test showroom."""
    from app.models.showroom import Showroom

    showroom = Showroom(
        slug="test-showroom",
        name="Test Showroom",
        headline="Test headline",
        description="Test description",
        status="active",
        sort_order=0,
    )
    db.add(showroom)
    db.commit()
    db.refresh(showroom)
    return showroom


@pytest.fixture
def test_asset(db: Session, test_showroom):
    """Create a test asset with commerce fields."""
    from app.models.asset import Asset

    asset = Asset(
        showroom_id=test_showroom.id,
        slug="test-asset",
        name="Test Asset",
        headline="Test headline",
        description="Test description",
        status="active",
        sort_order=0,
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=Decimal("0.03"),
        price_nominal_eur=Decimal("0.09"),
        sold_special_fractions=0,
        is_active=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture
def test_asset_inactive(db: Session, test_showroom):
    """Create an inactive test asset."""
    from app.models.asset import Asset

    asset = Asset(
        showroom_id=test_showroom.id,
        slug="inactive-asset",
        name="Inactive Asset",
        headline="Inactive headline",
        description="Inactive description",
        status="active",
        sort_order=1,
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=Decimal("0.03"),
        price_nominal_eur=Decimal("0.09"),
        sold_special_fractions=0,
        is_active=False,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture
def test_wallet(db: Session, test_user):
    """Create a blockchain wallet for the test user."""
    from app.models.blockchain_wallet import BlockchainWallet

    wallet = BlockchainWallet(
        user_id=test_user.id,
        address="0xaabbccdd11223344556677889900aabbccddeeff",
        encrypted_private_key="test-encrypted-key",
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@pytest.fixture
def test_wallet2(db: Session, test_user2):
    """Create a blockchain wallet for the second test user."""
    from app.models.blockchain_wallet import BlockchainWallet

    wallet = BlockchainWallet(
        user_id=test_user2.id,
        address="0x1122334455667788990011223344556677889900",
        encrypted_private_key="test-encrypted-key-2",
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@pytest.fixture
def test_fraction_transfer(db: Session, test_asset, test_user):
    """Create a sample fraction transfer."""
    from app.models.fraction_transfer import FractionTransfer

    transfer = FractionTransfer(
        asset_id=test_asset.id,
        from_user_id=None,
        to_user_id=test_user.id,
        fraction_count=100,
        transfer_type="purchase",
        blockchain_status="confirmed",
        blockchain_tx_hash="0xdeadbeef",
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return transfer


@pytest.fixture
def auth_token(client: TestClient, test_user) -> str:
    """Get auth token for test user."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 200
    return response.json()["accessToken"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Get auth headers with token."""
    return {"Authorization": f"Bearer {auth_token}"}
