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
    PaymentMethodsResponse,
)
from app.services.payment_gateways import (
    CheckoutResult,
    PaymentGateway,
    get_enabled_payment_methods,
    get_payment_gateways,
)
from app.services.url_utils import validate_checkout_redirect_url

router = APIRouter()


def _get_payment_gateway_or_raise(payment_method: str) -> PaymentGateway:
    gateway = get_payment_gateways().get(payment_method)
    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported payment method: {payment_method}",
        )
    if not gateway.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Payment method {payment_method} is currently unavailable",
        )
    return gateway


def _get_active_lot_or_raise(db: Session, lot_id: int) -> Lot:
    lot = db.query(Lot).filter(Lot.id == lot_id, Lot.is_active.is_(True)).first()
    if not lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot not found")
    return lot


def _remaining_special_fractions(lot: Lot) -> int:
    return max(0, lot.special_price_fractions_cap - lot.sold_special_fractions)


def _validate_fraction_count_or_raise(fraction_count: int, lot: Lot) -> None:
    remaining = _remaining_special_fractions(lot)
    min_f = settings.MIN_FRACTIONS
    if fraction_count < min_f:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum {min_f} fractions required",
        )
    if fraction_count > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {remaining} fractions available at special price",
        )


def _resolve_checkout_urls(body: OrderCreateRequest, gateway: PaymentGateway) -> tuple[str, str]:
    success_url = body.return_url or gateway.success_url
    cancel_url = body.cancel_url or gateway.cancel_url
    if body.return_url:
        success_url = validate_checkout_redirect_url(body.return_url, "return_url")
    if body.cancel_url:
        cancel_url = validate_checkout_redirect_url(body.cancel_url, "cancel_url")
    return success_url, cancel_url


def _calculate_amount_eur_cents(lot: Lot, fraction_count: int) -> int:
    # Use Decimal for precise conversion to cents.
    price_special_decimal = Decimal(str(lot.price_special_eur))
    return int(price_special_decimal * Decimal("100") * Decimal(str(fraction_count)))


def _create_pending_order(
    db: Session,
    *,
    current_user: User,
    lot: Lot,
    fraction_count: int,
    amount_eur_cents: int,
    payment_method: str,
) -> Order:
    order = Order(
        user_id=current_user.id,
        lot_id=lot.id,
        fraction_count=fraction_count,
        amount_eur_cents=amount_eur_cents,
        payment_method=payment_method,
        status="pending",
    )
    db.add(order)
    db.flush()
    return order


def _create_checkout_or_raise(
    db: Session,
    *,
    gateway: PaymentGateway,
    order: Order,
    lot: Lot,
    amount_eur_cents: int,
    success_url: str,
    cancel_url: str,
) -> CheckoutResult:
    try:
        result = gateway.create_checkout(
            order_id=order.id,
            amount_eur_cents=amount_eur_cents,
            fraction_count=order.fraction_count,
            lot_name=lot.name,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )

    if not result.checkout_url:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )
    return result


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
    Create an order for the given lot and fraction count.
    Validates min/max fractions. Returns checkout_url for redirect (Stripe or PayKilla).
    """
    gateway = _get_payment_gateway_or_raise(body.payment_method)
    lot = _get_active_lot_or_raise(db, body.lot_id)
    _validate_fraction_count_or_raise(body.fraction_count, lot)
    success_url, cancel_url = _resolve_checkout_urls(body, gateway)
    amount_eur_cents = _calculate_amount_eur_cents(lot, body.fraction_count)
    order = _create_pending_order(
        db,
        current_user=current_user,
        lot=lot,
        fraction_count=body.fraction_count,
        amount_eur_cents=amount_eur_cents,
        payment_method=body.payment_method,
    )
    result = _create_checkout_or_raise(
        db,
        gateway=gateway,
        order=order,
        lot=lot,
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
