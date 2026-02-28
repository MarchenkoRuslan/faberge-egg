"""Symbol blockchain adapter that calls API-Gateway (Express + Symbol SDK)."""

from __future__ import annotations

import logging
import re
import uuid

import httpx

from app.core.config import settings
from app.shared.blockchain_service import (
    TransferResult,
    WalletKeyPair,
)

logger = logging.getLogger(__name__)

# Mosaic ID is 16 hex chars
_MOSAIC_ID_PATTERN = re.compile(r"^[0-9A-Fa-f]{16}$")


def _base_url() -> str:
    url = settings.BLOCKCHAIN_RPC_URL.rstrip("/")
    return url


def _get_address_from_response(data: dict) -> str:
    """Extract address string from API-Gateway account/create response."""
    addr = data.get("address")
    if isinstance(addr, dict):
        return addr.get("address", addr.get("plain", "")) or ""
    return str(addr) if addr else ""


class SymbolBlockchainService:
    """BlockchainService implementation that calls API-Gateway (Symbol blockchain)."""

    def __init__(
        self,
        base_url: str,
        platform_private_key: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._platform_key = platform_private_key

    def create_wallet(self) -> WalletKeyPair:
        """Generate a new Symbol wallet via API-Gateway POST /api/account/create."""
        user_id = str(uuid.uuid4())
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self._base_url}/api/account/create",
                json={"userId": user_id},
            )
            resp.raise_for_status()
            data = resp.json()
        address = _get_address_from_response(data)
        private_key = data.get("privateKey", "")
        if not address or not private_key:
            raise ValueError(
                "API-Gateway account/create did not return address and privateKey"
            )
        logger.info("symbol blockchain: created wallet address=%s", address)
        return WalletKeyPair(address=address, private_key=private_key)

    def check_fraction_availability(
        self, contract_ref: str, requested_count: int, total_available: int
    ) -> bool:
        """Check if requested fractions are available (local check)."""
        available = requested_count <= total_available
        logger.info(
            "symbol blockchain: check_fraction_availability "
            "contract=%s requested=%d available=%d result=%s",
            contract_ref,
            requested_count,
            total_available,
            available,
        )
        return available

    def transfer_fractions(
        self,
        from_address: str,
        to_address: str,
        contract_ref: str,
        count: int,
    ) -> TransferResult:
        """Initiate fraction transfer via API-Gateway. Uses platform key when from_address is 'platform'."""
        private_key = (
            self._platform_key if from_address == "platform" else None
        )
        if not private_key:
            raise ValueError(
                "transfer_fractions from platform requires BLOCKCHAIN_PLATFORM_PRIVATE_KEY"
            )
        if not contract_ref or count < 1:
            raise ValueError("contract_ref and count must be set")

        use_mosaic_id = bool(_MOSAIC_ID_PATTERN.match(contract_ref.strip()))
        message = f"fraction_transfer count={count}"

        with httpx.Client(timeout=60.0) as client:
            if use_mosaic_id:
                resp = client.put(
                    f"{self._base_url}/api/transaction/sendMosaic",
                    json={
                        "senderPrivateKey": private_key,
                        "recipientAddress": to_address,
                        "amount": count,
                        "mosaicId": contract_ref,
                        "message": message,
                    },
                )
            else:
                resp = client.put(
                    f"{self._base_url}/api/transaction/send",
                    json={
                        "senderPrivateKey": private_key,
                        "recipientAddress": to_address,
                        "amount": count,
                        "namespaceName": contract_ref,
                        "message": message,
                    },
                )
            resp.raise_for_status()
            data = resp.json()

        tx_hash = data.get("hash") or (data.get("meta") or {}).get("hash") or ""
        status = "confirmed" if data.get("group") == "confirmed" else "pending"

        logger.info(
            "symbol blockchain: transfer_fractions from=%s to=%s contract=%s count=%d tx_hash=%s",
            from_address,
            to_address,
            contract_ref,
            count,
            tx_hash,
        )
        return TransferResult(tx_hash=tx_hash, status=status)

    def get_transaction_status(self, tx_hash: str) -> str:
        """Query transaction status via API-Gateway GET /api/transaction/getStatus/:hash."""
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{self._base_url}/api/transaction/getStatus/{tx_hash}",
            )
            resp.raise_for_status()
            data = resp.json()
        group = data.get("group", "").lower()
        if group == "confirmed":
            return "confirmed"
        if group == "failed":
            return "failed"
        return "pending"
