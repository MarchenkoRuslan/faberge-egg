from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.blockchain_wallet import BlockchainWallet
from app.shared.blockchain_service import get_blockchain_service

logger = logging.getLogger(__name__)

# Cached Fernet instance when using ephemeral key (dev/test only).
# Ensures consistent encryption/decryption within process lifetime.
_cached_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _cached_fernet
    key = settings.WALLET_ENCRYPTION_KEY
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    if _cached_fernet is not None:
        return _cached_fernet
    ephemeral_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    logger.warning(
        "WALLET_ENCRYPTION_KEY is not set; generated ephemeral key (cached for process). "
        "Encrypted wallet keys will be unrecoverable after restart.",
    )
    _cached_fernet = Fernet(ephemeral_key.encode())
    return _cached_fernet


def _encrypt_private_key(private_key: str) -> str:
    f = _get_fernet()
    return f.encrypt(private_key.encode()).decode()


def _decrypt_private_key(encrypted_key: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()


def create_user_wallet(user_id: int, db: Session) -> BlockchainWallet:
    """Create a blockchain wallet for a user.

    Generates a key pair via the blockchain service, encrypts the private key,
    and persists the wallet record. Raises if user already has a wallet.
    """
    existing = db.query(BlockchainWallet).filter(
        BlockchainWallet.user_id == user_id,
    ).first()
    if existing:
        logger.info("wallet already exists for user_id=%d", user_id)
        return existing

    bc = get_blockchain_service()
    key_pair = bc.create_wallet()

    wallet = BlockchainWallet(
        user_id=user_id,
        address=key_pair.address,
        encrypted_private_key=_encrypt_private_key(key_pair.private_key),
    )
    db.add(wallet)
    db.flush()
    logger.info(
        "created blockchain wallet for user_id=%d address=%s",
        user_id, key_pair.address,
    )
    return wallet


def get_user_wallet(user_id: int, db: Session) -> BlockchainWallet | None:
    """Return the blockchain wallet for a user, or None."""
    return db.query(BlockchainWallet).filter(
        BlockchainWallet.user_id == user_id,
    ).first()


def get_wallet_address(user_id: int, db: Session) -> str | None:
    """Return just the blockchain address for a user, or None."""
    wallet = get_user_wallet(user_id, db)
    return wallet.address if wallet else None


def decrypt_wallet_private_key(wallet: BlockchainWallet) -> str:
    """Decrypt and return the private key. Use with caution."""
    return _decrypt_private_key(wallet.encrypted_private_key)


def ensure_both_have_wallets(
    buyer_id: int, seller_id: int | None, db: Session,
) -> tuple[BlockchainWallet, BlockchainWallet | None]:
    """Ensure buyer has a wallet; optionally check seller too.

    Returns (buyer_wallet, seller_wallet). Seller wallet is None when
    seller_id is None (platform/mint transfers).
    """
    buyer_wallet = get_user_wallet(buyer_id, db)
    if not buyer_wallet:
        buyer_wallet = create_user_wallet(buyer_id, db)

    seller_wallet = None
    if seller_id is not None:
        seller_wallet = get_user_wallet(seller_id, db)
        if not seller_wallet:
            seller_wallet = create_user_wallet(seller_id, db)

    return buyer_wallet, seller_wallet
