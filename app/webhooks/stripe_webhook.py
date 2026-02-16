import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lot, Order, get_db

router = APIRouter()
logger = logging.getLogger(__name__)


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
    mark order as paid and increment lot sold_special_fractions.
    Idempotent: if order already paid, no double spend.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set, skipping webhook verification")
        return {"received": True}

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id_str = session.get("metadata", {}).get("order_id")
        if not order_id_str:
            logger.warning("No order_id in session metadata")
            return {"received": True}

        try:
            order_id = int(order_id_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid order_id format: {order_id_str}, error: {e}")
            return {"received": True}

        if order_id <= 0:
            logger.warning(f"Invalid non-positive order_id: {order_id}")
            return {"received": True}

        try:
            order = db.query(Order).filter(Order.id == order_id).with_for_update().first()
            if not order:
                logger.warning(f"Order {order_id} not found")
                return {"received": True}

            if order.payment_method != "stripe":
                logger.warning(f"Order {order_id} payment method is {order.payment_method}, not stripe")
                return {"received": True}

            if order.status == "paid":
                logger.info(f"Order {order_id} already paid, skipping")
                return {"received": True}


            amount_total = session.get("amount_total")
            if amount_total is not None:
                try:
                    amount_total_cents = int(amount_total)
                except (TypeError, ValueError):
                    logger.warning("Invalid Stripe amount_total for order %s: %s", order_id, amount_total)
                    db.rollback()
                    return {"received": True}
                if amount_total_cents != order.amount_eur_cents:
                    logger.warning(
                        "Stripe amount mismatch for order %s: expected=%s, received=%s",
                        order_id,
                        order.amount_eur_cents,
                        amount_total_cents,
                    )
                    db.rollback()
                    return {"received": True}

            currency = session.get("currency")
            if currency and str(currency).lower() != "eur":
                logger.warning("Stripe currency mismatch for order %s: %s", order_id, currency)
                db.rollback()
                return {"received": True}

            lot = db.query(Lot).filter(Lot.id == order.lot_id).with_for_update().first()
            if not lot:
                logger.error(f"Lot {order.lot_id} not found for order {order_id}")
                db.rollback()
                return {"received": True}

            remaining = max(0, lot.special_price_fractions_cap - (lot.sold_special_fractions or 0))
            if order.fraction_count > remaining:
                logger.warning(
                    "Cannot mark order %s as paid: %s fractions requested, %s remaining",
                    order_id,
                    order.fraction_count,
                    remaining,
                )
                db.rollback()
                return {"received": True}

            order.status = "paid"
            order.external_payment_id = session.get("id") or session.get("payment_intent")
            lot.sold_special_fractions = (lot.sold_special_fractions or 0) + order.fraction_count
            db.commit()
            logger.info(f"Order {order_id} marked as paid, lot {lot.id} updated")
        except Exception as e:
            logger.error(f"Error processing order {order_id}: {e}", exc_info=True)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    return {"received": True}
