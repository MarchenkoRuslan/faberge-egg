import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
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

SUCCESSFUL_PAYKILLA_STATUSES = {"success", "paid", "completed", "confirmed"}


def is_successful_payment_status(status_value: str | None) -> bool:
    """Return True when PayKilla callback status means payment is successful."""
    if status_value is None:
        return True
    return status_value.strip().lower() in SUCCESSFUL_PAYKILLA_STATUSES


def _verify_paykilla_signature(raw_body: bytes, signature: str | None) -> None:
    """Validate HMAC SHA-256 signature when PAYKILLA_WEBHOOK_SECRET is configured."""
    if not settings.PAYKILLA_WEBHOOK_SECRET:
        logger.warning("PAYKILLA_WEBHOOK_SECRET is not set, skipping webhook verification")
        return

    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")

    expected = hmac.new(
        settings.PAYKILLA_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


def _parse_paykilla_json_body(raw_body: bytes) -> dict:
    try:
        body = json.loads(raw_body)
    except Exception as exc:
        logger.error("Invalid JSON in PayKilla webhook: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")
    return body


def _parse_positive_int(value: object, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        logger.error("Invalid %s format: %s, error: %s", field_name, value, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be integer",
        ) from exc
    if parsed <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be positive",
        )
    return parsed


def _parse_order_id(body: dict) -> int:
    if body.get("order_id") is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id required")
    return _parse_positive_int(body.get("order_id"), field_name="order_id")


def _parse_optional_amount(body: dict) -> int | None:
    if body.get("amount_eur_cents") is None:
        return None
    return _parse_positive_int(body.get("amount_eur_cents"), field_name="amount_eur_cents")


@router.post(
    "/paykilla",
    summary="PayKilla webhook/callback",
)
async def paykilla_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """
    PayKilla callback for successful crypto payment.
    Expects JSON body with order_id (and optionally status, transaction_id).
    Idempotent: if order already paid, no double spend.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-paykilla-signature")
    _verify_paykilla_signature(raw_body, signature)

    body = _parse_paykilla_json_body(raw_body)
    order_id = _parse_order_id(body)

    payment_status = body.get("status")
    if not is_successful_payment_status(payment_status):
        logger.info("Ignoring PayKilla webhook for order %s with status: %s", order_id, payment_status)
        return {"received": True}

    external_id = body.get("transaction_id") or body.get("payment_id")
    callback_amount_cents = _parse_optional_amount(body)

    try:
        result = settle_order_payment(
            db,
            order_id=order_id,
            expected_payment_method="paykilla",
            external_payment_id=external_id,
            callback_amount_cents=callback_amount_cents,
        )
    except Exception as exc:
        logger.error("Error processing order %s: %s", order_id, exc, exc_info=True)
        return {"received": True}

    log_settlement_result(result, "paykilla")

    return {"received": True}
