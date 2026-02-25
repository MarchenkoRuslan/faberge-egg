import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import get_db
from app.services.payment_settlement import (
    PaymentSettlementResult,
    PaymentSettlementStatus,
    settle_order_payment,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _construct_stripe_event(payload: bytes, sig_header: str) -> dict | None:
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set, skipping webhook verification")
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as exc:
        logger.error("Invalid payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload") from exc
    except stripe.SignatureVerificationError as exc:
        logger.error("Invalid signature: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc
    if not isinstance(event, dict):
        return dict(event)
    return event


def _get_checkout_session_from_event(event: dict) -> dict | None:
    if event.get("type") != "checkout.session.completed":
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    session = data.get("object")
    if not isinstance(session, dict):
        return None
    return session


def _parse_stripe_order_id(session: dict) -> int | None:
    metadata = session.get("metadata")
    if not isinstance(metadata, dict):
        logger.warning("No order_id in session metadata")
        return None
    order_id_str = metadata.get("order_id")
    if not order_id_str:
        logger.warning("No order_id in session metadata")
        return None
    try:
        order_id = int(order_id_str)
    except (ValueError, TypeError) as exc:
        logger.error("Invalid order_id format: %s, error: %s", order_id_str, exc)
        return None
    if order_id <= 0:
        logger.warning("Invalid non-positive order_id: %s", order_id)
        return None
    return order_id


def _parse_stripe_amount_total(session: dict, order_id: int) -> tuple[bool, int | None]:
    amount_total = session.get("amount_total")
    if amount_total is None:
        return True, None
    try:
        return True, int(amount_total)
    except (TypeError, ValueError):
        logger.warning("Invalid Stripe amount_total for order %s: %s", order_id, amount_total)
        return False, None


def _validate_stripe_currency(session: dict, order_id: int) -> bool:
    currency = session.get("currency")
    if not currency:
        return True
    if str(currency).lower() == "eur":
        return True
    logger.warning("Stripe currency mismatch for order %s: %s", order_id, currency)
    return False


def _log_stripe_settlement_result(result: PaymentSettlementResult) -> None:
    if result.status == PaymentSettlementStatus.PAID:
        logger.info("Order %s marked as paid, asset %s updated", result.order_id, result.asset_id)
        return
    if result.status == PaymentSettlementStatus.ALREADY_PAID:
        logger.info("Order %s already paid, skipping", result.order_id)
        return
    if result.status == PaymentSettlementStatus.ORDER_NOT_FOUND:
        logger.warning("Order %s not found", result.order_id)
        return
    if result.status == PaymentSettlementStatus.WRONG_PAYMENT_METHOD:
        logger.warning(
            "Order %s payment method is %s, not stripe",
            result.order_id,
            result.actual_payment_method,
        )
        return
    if result.status == PaymentSettlementStatus.AMOUNT_MISMATCH:
        logger.warning(
            "Stripe amount mismatch for order %s: expected=%s, received=%s",
            result.order_id,
            result.expected_amount_cents,
            result.received_amount_cents,
        )
        return
    if result.status == PaymentSettlementStatus.ASSET_NOT_FOUND:
        logger.error("Asset %s not found for order %s", result.asset_id, result.order_id)
        return
    if result.status == PaymentSettlementStatus.CAPACITY_EXCEEDED:
        logger.warning(
            "Cannot mark order %s as paid: %s fractions requested, %s remaining",
            result.order_id,
            result.requested_fractions,
            result.remaining_fractions,
        )


def _handle_checkout_session_completed(session: dict, db: Session) -> None:
    order_id = _parse_stripe_order_id(session)
    if order_id is None:
        return

    amount_ok, amount_total_cents = _parse_stripe_amount_total(session, order_id)
    if not amount_ok:
        db.rollback()
        return

    if not _validate_stripe_currency(session, order_id):
        db.rollback()
        return

    try:
        result = settle_order_payment(
            db,
            order_id=order_id,
            expected_payment_method="stripe",
            external_payment_id=session.get("id") or session.get("payment_intent"),
            callback_amount_cents=amount_total_cents,
        )
    except Exception as exc:
        logger.error("Error processing order %s: %s", order_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    _log_stripe_settlement_result(result)


@router.post(
    "/stripe",
    summary="Stripe webhook",
)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Stripe sends events here. We handle checkout.session.completed:
    mark order as paid and increment asset sold_special_fractions.
    Idempotent: if order already paid, no double spend.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    event = _construct_stripe_event(payload, sig_header)
    if event is None:
        return {"received": True}

    session = _get_checkout_session_from_event(event)
    if session is not None:
        _handle_checkout_session_completed(session, db)

    return {"received": True}
