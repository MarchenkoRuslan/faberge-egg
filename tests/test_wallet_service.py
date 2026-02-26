import pytest
from sqlalchemy.orm import Session

from app.models.blockchain_wallet import BlockchainWallet
from app.services.blockchain_service import reset_blockchain_service
from app.services.wallet_service import (
    create_user_wallet,
    decrypt_wallet_private_key,
    ensure_both_have_wallets,
    get_user_wallet,
    get_wallet_address,
)


class TestCreateUserWallet:
    def setup_method(self):
        reset_blockchain_service()

    def teardown_method(self):
        reset_blockchain_service()

    def test_creates_wallet(self, db: Session, test_user):
        wallet = create_user_wallet(test_user.id, db)
        db.commit()

        assert isinstance(wallet, BlockchainWallet)
        assert wallet.user_id == test_user.id
        assert wallet.address.startswith("0x")
        assert wallet.encrypted_private_key

    def test_idempotent(self, db: Session, test_user):
        w1 = create_user_wallet(test_user.id, db)
        db.commit()
        w2 = create_user_wallet(test_user.id, db)
        assert w1.id == w2.id

    def test_encrypted_key_is_decryptable(self, db: Session, test_user):
        wallet = create_user_wallet(test_user.id, db)
        db.commit()
        decrypted = decrypt_wallet_private_key(wallet)
        assert decrypted.startswith("0x")
        assert len(decrypted) > 10


class TestGetUserWallet:
    def test_returns_wallet_when_exists(self, db: Session, test_user, test_wallet):
        wallet = get_user_wallet(test_user.id, db)
        assert wallet is not None
        assert wallet.address == test_wallet.address

    def test_returns_none_when_no_wallet(self, db: Session, test_user):
        assert get_user_wallet(test_user.id, db) is None


class TestGetWalletAddress:
    def test_returns_address(self, db: Session, test_user, test_wallet):
        address = get_wallet_address(test_user.id, db)
        assert address == test_wallet.address

    def test_returns_none_without_wallet(self, db: Session, test_user):
        assert get_wallet_address(test_user.id, db) is None


class TestEnsureBothHaveWallets:
    def setup_method(self):
        reset_blockchain_service()

    def teardown_method(self):
        reset_blockchain_service()

    def test_creates_wallets_for_both(self, db: Session, test_user, test_user2):
        buyer_w, seller_w = ensure_both_have_wallets(
            test_user.id, test_user2.id, db,
        )
        db.commit()

        assert buyer_w.user_id == test_user.id
        assert seller_w is not None
        assert seller_w.user_id == test_user2.id

    def test_seller_none_for_platform(self, db: Session, test_user):
        buyer_w, seller_w = ensure_both_have_wallets(
            test_user.id, None, db,
        )
        db.commit()

        assert buyer_w.user_id == test_user.id
        assert seller_w is None

    def test_uses_existing_wallets(
        self, db: Session, test_user, test_user2, test_wallet, test_wallet2,
    ):
        buyer_w, seller_w = ensure_both_have_wallets(
            test_user.id, test_user2.id, db,
        )
        assert buyer_w.id == test_wallet.id
        assert seller_w is not None
        assert seller_w.id == test_wallet2.id
