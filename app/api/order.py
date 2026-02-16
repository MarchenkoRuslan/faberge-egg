from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user
from app.models import Lot, Order, User, get_db
from app.schemas.orders import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderResponse,
    OrderStatusResponse,
)
from app.services import paykilla_service, stripe_service

router = APIRouter()


@router.post(
    "",
    response_model=OrderCreateResponse,
    summary="Create order and get checkout URL",
)
def create_order(
    body: OrderCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Create an order for the given lot and fraction count.
    Validates min/max fractions. Returns checkout_url for redirect (Stripe or PayKilla).
    """
    lot = db.query(Lot).filter(Lot.id == body.lot_id, Lot.is_active == True).first()
    if not lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot not found")

    remaining = max(0, lot.special_price_fractions_cap - lot.sold_special_fractions)
    min_f = settings.MIN_FRACTIONS
    if body.fraction_count < min_f:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum {min_f} fractions required",
        )
    if body.fraction_count > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {remaining} fractions available at special price",
        )

    # Price in cents (special price €0.03 -> 3 cents per fraction)
    # Use Decimal for precise calculation
    price_special_decimal = Decimal(str(lot.price_special_eur))
    amount_eur_cents = int(price_special_decimal * Decimal("100") * Decimal(str(body.fraction_count)))

    order = Order(
        user_id=current_user.id,
        lot_id=lot.id,
        fraction_count=body.fraction_count,
        amount_eur_cents=amount_eur_cents,
        payment_method=body.payment_method,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    success_url = body.return_url or (
        settings.STRIPE_SUCCESS_URL if body.payment_method == "stripe" else settings.PAYKILLA_SUCCESS_URL
    )
    cancel_url = body.cancel_url or (
        settings.STRIPE_CANCEL_URL if body.payment_method == "stripe" else settings.PAYKILLA_CANCEL_URL
    )

    checkout_url = None
    session_id = None
    try:
        if body.payment_method == "stripe":
            result = stripe_service.create_checkout_session(
                order_id=order.id,
                amount_eur_cents=amount_eur_cents,
                fraction_count=body.fraction_count,
                lot_name=lot.name,
                success_url=success_url,
                cancel_url=cancel_url,
            )
            if isinstance(result, tuple):
                checkout_url, session_id = result
            else:
                checkout_url = result
        elif body.payment_method == "paykilla":
            checkout_url = paykilla_service.create_payment(
                order_id=order.id,
                amount_eur_cents=amount_eur_cents,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported payment method: {body.payment_method}",
            )

        if checkout_url is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create checkout session",
            )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )

    return OrderCreateResponse(
        order_id=order.id,
        checkout_url=checkout_url,
        session_id=session_id,
        payment_method=body.payment_method,
    )


@router.get(
    "/me",
    response_model=list[OrderResponse],
    summary="List my orders",
)
def my_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Returns the list of orders for the current user."""
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.created_at.desc()).all()
    return [
        OrderResponse(
            id=o.id,
            lot_id=o.lot_id,
            fraction_count=o.fraction_count,
            amount_eur_cents=o.amount_eur_cents,
            payment_method=o.payment_method,
            status=o.status,
            created_at=o.created_at.isoformat() if o.created_at else "",
        )
        for o in orders
    ]


@router.get(
    "/{order_id}/status",
    response_model=OrderStatusResponse,
    summary="Get order status",
)
def order_status(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Returns status of an order (only for the current user's orders)."""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderStatusResponse(
        id=order.id,
        status=order.status,
        fraction_count=order.fraction_count,
        amount_eur_cents=order.amount_eur_cents,
    )
