import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Asset, Order
from app.models.fraction_transfer import FractionTransfer
from app.services.blockchain_service import get_blockchain_service
from app.services.upsale_campaign_service import create_campaign, on_upsale_purchase
from app.services.wallet_service import get_wallet_address

logger = logging.getLogger(__name__)


class PaymentSettlementStatus(str, Enum):
    PAID = "paid"
    ALREADY_PAID = "already_paid"
    ORDER_NOT_FOUND = "order_not_found"
    WRONG_PAYMENT_METHOD = "wrong_payment_method"
    AMOUNT_MISMATCH = "amount_mismatch"
    ASSET_NOT_FOUND = "asset_not_found"
    CAPACITY_EXCEEDED = "capacity_exceeded"


@dataclass(frozen=True)
class PaymentSettlementResult:
    status: PaymentSettlementStatus
    order_id: int
    asset_id: int | None = None
    actual_payment_method: str | None = None
    expected_payment_method: str | None = None
    expected_amount_cents: int | None = None
    received_amount_cents: int | None = None
    requested_fractions: int | None = None
    remaining_fractions: int | None = None


def _rollback_and_result(db: Session, result: PaymentSettlementResult) -> PaymentSettlementResult:
    db.rollback()
    return result


def _load_order(db: Session, order_id: int) -> Order | None:
    return db.query(Order).filter(Order.id == order_id).with_for_update().first()


def _load_asset(db: Session, asset_id: int) -> Asset | None:
    return db.query(Asset).filter(Asset.id == asset_id).with_for_update().first()


def _remaining_special_fractions(asset: Asset) -> int:
    return max(0, asset.special_price_fractions_cap - (asset.sold_special_fractions or 0))


def _validate_order_for_settlement(
    db: Session,
    *,
    order: Order,
    expected_payment_method: str,
    callback_amount_cents: int | None,
) -> PaymentSettlementResult | None:
    if order.payment_method != expected_payment_method:
        return _rollback_and_result(
            db,
            PaymentSettlementResult(
                status=PaymentSettlementStatus.WRONG_PAYMENT_METHOD,
                order_id=order.id,
                asset_id=order.asset_id,
                actual_payment_method=order.payment_method,
                expected_payment_method=expected_payment_method,
            ),
        )
    if order.status == "paid":
        return _rollback_and_result(
            db,
            PaymentSettlementResult(
                status=PaymentSettlementStatus.ALREADY_PAID,
                order_id=order.id,
                asset_id=order.asset_id,
            ),
        )
    if callback_amount_cents is not None and callback_amount_cents != order.amount_eur_cents:
        return _rollback_and_result(
            db,
            PaymentSettlementResult(
                status=PaymentSettlementStatus.AMOUNT_MISMATCH,
                order_id=order.id,
                asset_id=order.asset_id,
                expected_amount_cents=order.amount_eur_cents,
                received_amount_cents=callback_amount_cents,
            ),
        )
    return None


def _validate_asset_capacity(
    db: Session,
    *,
    order: Order,
    asset: Asset,
) -> PaymentSettlementResult | None:
    remaining = _remaining_special_fractions(asset)
    if order.fraction_count > remaining:
        return _rollback_and_result(
            db,
            PaymentSettlementResult(
                status=PaymentSettlementStatus.CAPACITY_EXCEEDED,
                order_id=order.id,
                asset_id=asset.id,
                requested_fractions=order.fraction_count,
                remaining_fractions=remaining,
            ),
        )
    return None


def _record_fraction_transfer(
    db: Session, *, order: Order, asset: Asset,
) -> FractionTransfer | None:
    """Create a FractionTransfer provenance record for a settled order.

    Uses a SAVEPOINT so that a failure here does not poison the session
    and cause the outer commit (order + asset updates) to raise
    PendingRollbackError.
    """
    try:
        with db.begin_nested():
            transfer = FractionTransfer(
                asset_id=asset.id,
                from_user_id=None,
                to_user_id=order.user_id,
                fraction_count=order.fraction_count,
                transfer_type="purchase",
                order_id=order.id,
                blockchain_status="pending",
            )
            db.add(transfer)
            db.flush()
        return transfer
    except Exception:
        logger.exception(
            "Failed to create FractionTransfer for order_id=%d", order.id,
        )
        return None


def _attempt_blockchain_transfer(
    db: Session, *, transfer: FractionTransfer, order: Order,
) -> None:
    """If blockchain is enabled, initiate the on-chain fraction transfer."""
    if not settings.BLOCKCHAIN_ENABLED:
        return

    try:
        buyer_address = get_wallet_address(order.user_id, db)
        if not buyer_address:
            logger.warning(
                "blockchain transfer skipped: buyer user_id=%d has no wallet",
                order.user_id,
            )
            return

        bc = get_blockchain_service()
        result = bc.transfer_fractions(
            from_address="platform",
            to_address=buyer_address,
            contract_ref=settings.BLOCKCHAIN_CONTRACT_ADDRESS,
            count=order.fraction_count,
        )
        transfer.blockchain_tx_hash = result.tx_hash
        transfer.blockchain_status = result.status
        db.commit()
    except Exception:
        logger.exception(
            "blockchain transfer failed for order_id=%d transfer_id=%d "
            "(provenance record preserved, tx can be retried)",
            order.id, transfer.id,
        )


def _trigger_upsale_campaign(db: Session, *, order: Order) -> None:
    """Start or advance an upsale campaign after a successful payment.

    Failures here must never affect the payment result.
    """
    try:
        advanced = on_upsale_purchase(db, order)
        if not advanced:
            create_campaign(db, order)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Upsale campaign hook failed for order_id=%d (payment unaffected)",
            order.id,
        )


def settle_order_payment(
    db: Session,
    *,
    order_id: int,
    expected_payment_method: str,
    external_payment_id: str | None,
    callback_amount_cents: int | None = None,
) -> PaymentSettlementResult:
    """Mark an order as paid and increment asset sold fractions when validations pass."""
    try:
        order = _load_order(db, order_id)
        if not order:
            return _rollback_and_result(
                db,
                PaymentSettlementResult(
                    status=PaymentSettlementStatus.ORDER_NOT_FOUND,
                    order_id=order_id,
                ),
            )

        order_validation_result = _validate_order_for_settlement(
            db,
            order=order,
            expected_payment_method=expected_payment_method,
            callback_amount_cents=callback_amount_cents,
        )
        if order_validation_result:
            return order_validation_result

        asset = _load_asset(db, order.asset_id)
        if not asset:
            return _rollback_and_result(
                db,
                PaymentSettlementResult(
                    status=PaymentSettlementStatus.ASSET_NOT_FOUND,
                    order_id=order.id,
                    asset_id=order.asset_id,
                ),
            )

        capacity_validation_result = _validate_asset_capacity(db, order=order, asset=asset)
        if capacity_validation_result:
            return capacity_validation_result

        asset.sold_special_fractions = (asset.sold_special_fractions or 0) + order.fraction_count
        order.status = "paid"
        order.external_payment_id = external_payment_id

        transfer = _record_fraction_transfer(db, order=order, asset=asset)
        db.commit()

        if transfer:
            _attempt_blockchain_transfer(db, transfer=transfer, order=order)

        _trigger_upsale_campaign(db, order=order)

        return PaymentSettlementResult(
            status=PaymentSettlementStatus.PAID,
            order_id=order.id,
            asset_id=asset.id,
        )
    except Exception:
        db.rollback()
        raise
