from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalletKeyPair:
    address: str
    private_key: str


@dataclass(frozen=True)
class TransferResult:
    tx_hash: str
    status: str  # "pending", "confirmed", "failed"


@runtime_checkable
class BlockchainService(Protocol):
    def create_wallet(self) -> WalletKeyPair:
        """Generate a new blockchain wallet key pair."""
        ...

    def check_fraction_availability(
        self, contract_ref: str, requested_count: int, total_available: int,
    ) -> bool:
        """Check if requested fractions are available in the FCC contract."""
        ...

    def transfer_fractions(
        self,
        from_address: str,
        to_address: str,
        contract_ref: str,
        count: int,
    ) -> TransferResult:
        """Initiate a fraction transfer between two blockchain accounts."""
        ...

    def get_transaction_status(self, tx_hash: str) -> str:
        """Query blockchain for current status of a transaction."""
        ...


class StubBlockchainService:
    """Development/test implementation that works without a real blockchain node."""

    def create_wallet(self) -> WalletKeyPair:
        address = "0x" + (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
        private_key = "0x" + (uuid.uuid4().hex + uuid.uuid4().hex)[:64]
        logger.info("stub blockchain: created wallet address=%s", address)
        return WalletKeyPair(address=address, private_key=private_key)

    def check_fraction_availability(
        self, contract_ref: str, requested_count: int, total_available: int,
    ) -> bool:
        available = requested_count <= total_available
        logger.info(
            "stub blockchain: check_fraction_availability "
            "contract=%s requested=%d available=%d result=%s",
            contract_ref, requested_count, total_available, available,
        )
        return available

    def transfer_fractions(
        self,
        from_address: str,
        to_address: str,
        contract_ref: str,
        count: int,
    ) -> TransferResult:
        tx_hash = "0x" + uuid.uuid4().hex
        logger.info(
            "stub blockchain: transfer_fractions "
            "from=%s to=%s contract=%s count=%d tx_hash=%s",
            from_address, to_address, contract_ref, count, tx_hash,
        )
        return TransferResult(tx_hash=tx_hash, status="confirmed")

    def get_transaction_status(self, tx_hash: str) -> str:
        logger.info("stub blockchain: get_transaction_status tx_hash=%s", tx_hash)
        return "confirmed"


_blockchain_service: BlockchainService | None = None


def get_blockchain_service() -> BlockchainService:
    """Factory: returns the configured blockchain service singleton.

    When BLOCKCHAIN_ENABLED is False (or no real implementation is wired),
    returns a StubBlockchainService.
    """
    global _blockchain_service
    if _blockchain_service is not None:
        return _blockchain_service

    if settings.BLOCKCHAIN_ENABLED and settings.BLOCKCHAIN_RPC_URL:
        logger.warning(
            "BLOCKCHAIN_ENABLED=true but no real blockchain adapter is "
            "registered yet; falling back to StubBlockchainService",
        )

    _blockchain_service = StubBlockchainService()
    return _blockchain_service


def set_blockchain_service(service: BlockchainService) -> None:
    """Replace the global blockchain service (for testing or real adapter registration)."""
    global _blockchain_service
    _blockchain_service = service


def reset_blockchain_service() -> None:
    """Reset to default (re-creates on next get_blockchain_service call)."""
    global _blockchain_service
    _blockchain_service = None
