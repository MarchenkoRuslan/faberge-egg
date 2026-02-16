import stripe
from fastapi import APIRouter, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lot, Order, get_db

router = APIRouter()


def get_db_session():
    return next(get_db())


@router.post(
    "/stripe",
    summary="Stripe webhook",
)
async def stripe_webhook(request: Request):
    """
    Stripe sends events here. We handle checkout.session.completed:
    mark order as paid and increment lot sold_special_fractions.
    Idempotent: if order already paid, no double spend.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    if not settings.STRIPE_WEBHOOK_SECRET:
        return {"received": True}
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id_str = session.get("metadata", {}).get("order_id")
        if not order_id_str:
            return {"received": True}
        try:
            order_id = int(order_id_str)
        except ValueError:
            return {"received": True}
        db: Session = get_db_session()
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return {"received": True}
            if order.status == "paid":
                return {"received": True}
            order.status = "paid"
            order.external_payment_id = session.get("id") or session.get("payment_intent")
            lot = db.query(Lot).filter(Lot.id == order.lot_id).first()
            if lot:
                lot.sold_special_fractions = (lot.sold_special_fractions or 0) + order.fraction_count
            db.commit()
        finally:
            db.close()
    return {"received": True}
