import logging

import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, status
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
        
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                logger.warning(f"Order {order_id} not found")
                return {"received": True}
            
            if order.status == "paid":
                logger.info(f"Order {order_id} already paid, skipping")
                return {"received": True}
            
            order.status = "paid"
            order.external_payment_id = session.get("id") or session.get("payment_intent")
            
            lot = db.query(Lot).filter(Lot.id == order.lot_id).first()
            if not lot:
                logger.error(f"Lot {order.lot_id} not found for order {order_id}")
                db.rollback()
                return {"received": True}
            
            lot.sold_special_fractions = (lot.sold_special_fractions or 0) + order.fraction_count
            db.commit()
            logger.info(f"Order {order_id} marked as paid, lot {lot.id} updated")
        except Exception as e:
            logger.error(f"Error processing order {order_id}: {e}", exc_info=True)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")
    
    return {"received": True}
