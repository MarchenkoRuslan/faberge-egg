from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Order, User
from app.domains.orders.schemas import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderResponse,
    OrderStatusResponse,
    PaymentMethodsResponse,
)
from app.domains.orders.service import (
    calculate_amount_eur_cents,
    create_checkout_or_raise,
    create_pending_order,
    get_active_asset_or_raise,
    get_enabled_payment_methods,
    get_payment_gateways,
    get_payment_gateway_or_raise,
    resolve_checkout_urls,
    validate_fraction_count_or_raise,
)

router = APIRouter()


@router.get(
    "/payment-methods",
    response_model=PaymentMethodsResponse,
    summary="List available and enabled payment methods",
)
def payment_methods():
    gateways = get_payment_gateways()
    return PaymentMethodsResponse(
        available_methods=list(gateways.keys()),
        enabled_methods=get_enabled_payment_methods(),
    )


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
    Create an order for the given asset and fraction count.
    Validates min/max fractions. Returns checkout_url for redirect (Stripe or PayKilla).
    """
    payment_method_str = body.payment_method.value
    gateway = get_payment_gateway_or_raise(payment_method_str)
    asset = get_active_asset_or_raise(db, body.asset_id)
    validate_fraction_count_or_raise(body.fraction_count, asset)
    success_url, cancel_url = resolve_checkout_urls(body, gateway)
    amount_eur_cents = calculate_amount_eur_cents(asset, body.fraction_count)
    order = create_pending_order(
        db,
        current_user=current_user,
        asset=asset,
        fraction_count=body.fraction_count,
        amount_eur_cents=amount_eur_cents,
        payment_method=payment_method_str,
    )
    result = create_checkout_or_raise(
        db,
        gateway=gateway,
        order=order,
        asset=asset,
        amount_eur_cents=amount_eur_cents,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    db.commit()

    return OrderCreateResponse(
        order_id=order.id,
        checkout_url=result.checkout_url,
        session_id=result.session_id,
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
            asset_id=o.asset_id,
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
