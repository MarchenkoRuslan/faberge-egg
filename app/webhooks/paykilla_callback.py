from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lot, Order, get_db

router = APIRouter()


def get_db_session():
    return next(get_db())


def mark_order_paid_and_increment_lot(order_id: int, external_id: str | None) -> bool:
    db: Session = get_db_session()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order or order.payment_method != "paykilla":
            return False
        if order.status == "paid":
            return True
        order.status = "paid"
        order.external_payment_id = external_id
        lot = db.query(Lot).filter(Lot.id == order.lot_id).first()
        if lot:
            lot.sold_special_fractions = (lot.sold_special_fractions or 0) + order.fraction_count
        db.commit()
        return True
    finally:
        db.close()


@router.post(
    "/paykilla",
    summary="PayKilla webhook/callback",
)
async def paykilla_webhook(request: Request):
    """
    PayKilla callback for successful crypto payment.
    Expects JSON body with order_id (and optionally status, transaction_id).
    Idempotent: if order already paid, no double spend.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    order_id = body.get("order_id")
    if order_id is None:
        raise HTTPException(status_code=400, detail="order_id required")
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="order_id must be integer")
    external_id = body.get("transaction_id") or body.get("payment_id")
    mark_order_paid_and_increment_lot(order_id, external_id)
    return {"received": True}
