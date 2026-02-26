import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.domains.payments.payment_settlement import (
    log_settlement_result,
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
    return data.get("object") if isinstance(data.get("object"), dict) else None


def _parse_stripe_order_id(session: dict) -> int | None:
    metadata = session.get("metadata")
    if not isinstance(metadata, dict):
        return None
    order_id_str = metadata.get("order_id")
    if not order_id_str:
        return None
    try:
        order_id = int(order_id_str)
        return order_id if order_id > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_stripe_amount_total(session: dict) -> tuple[bool, int | None]:
    amount_total = session.get("amount_total")
    if amount_total is None:
        return True, None
    try:
        return True, int(amount_total)
    except (TypeError, ValueError):
        return False, None


def _validate_stripe_currency(session: dict) -> bool:
    currency = session.get("currency")
    return not currency or str(currency).lower() == "eur"


def _handle_checkout_session_completed(session: dict, db: Session) -> None:
    order_id = _parse_stripe_order_id(session)
    if order_id is None:
        return
    amount_ok, amount_total_cents = _parse_stripe_amount_total(session)
    if not amount_ok:
        db.rollback()
        return
    if not _validate_stripe_currency(session):
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
    log_settlement_result(result, "stripe")


@router.post("/stripe", summary="Stripe webhook")
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    event = _construct_stripe_event(payload, sig_header)
    if event is None:
        return {"received": True}
    session = _get_checkout_session_from_event(event)
    if session is not None:
        _handle_checkout_session_completed(session, db)
    return {"received": True}
