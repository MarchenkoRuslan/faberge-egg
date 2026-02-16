import logging

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.models import Lot, Order, get_db

router = APIRouter()
logger = logging.getLogger(__name__)


SUCCESSFUL_PAYKILLA_STATUSES = {"success", "paid", "completed", "confirmed"}


def is_successful_payment_status(status_value: str | None) -> bool:
    """Return True when PayKilla callback status means payment is successful."""
    if status_value is None:
        return True
    return status_value.strip().lower() in SUCCESSFUL_PAYKILLA_STATUSES


def mark_order_paid_and_increment_lot(
    order_id: int,
    external_id: str | None,
    db: Session,
) -> bool:
    """Mark order as paid and increment lot sold fractions. Returns True if successful."""
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            logger.warning(f"Order {order_id} not found")
            return False
        
        if order.payment_method != "paykilla":
            logger.warning(f"Order {order_id} payment method is {order.payment_method}, not paykilla")
            return False
        
        if order.status == "paid":
            logger.info(f"Order {order_id} already paid, skipping")
            return True
        
        order.status = "paid"
        order.external_payment_id = external_id
        
        lot = db.query(Lot).filter(Lot.id == order.lot_id).first()
        if not lot:
            logger.error(f"Lot {order.lot_id} not found for order {order_id}")
            db.rollback()
            return False
        
        lot.sold_special_fractions = (lot.sold_special_fractions or 0) + order.fraction_count
        db.commit()
        logger.info(f"Order {order_id} marked as paid, lot {lot.id} updated")
        return True
    except Exception as e:
        logger.error(f"Error processing order {order_id}: {e}", exc_info=True)
        db.rollback()
        return False


@router.post(
    "/paykilla",
    summary="PayKilla webhook/callback",
)
async def paykilla_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    PayKilla callback for successful crypto payment.
    Expects JSON body with order_id (and optionally status, transaction_id).
    Idempotent: if order already paid, no double spend.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in PayKilla webhook: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")
    
    order_id = body.get("order_id")
    if order_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id required")
    
    try:
        order_id = int(order_id)
    except (TypeError, ValueError) as e:
        logger.error(f"Invalid order_id format: {order_id}, error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id must be integer")
    
    payment_status = body.get("status")
    if not is_successful_payment_status(payment_status):
        logger.info(f"Ignoring PayKilla webhook for order {order_id} with status: {payment_status}")
        return {"received": True}

    external_id = body.get("transaction_id") or body.get("payment_id")

    success = mark_order_paid_and_increment_lot(order_id, external_id, db)
    if not success:
        logger.warning(f"Failed to process PayKilla webhook for order {order_id}")
    
    return {"received": True}
