"""Order business logic: validation, checkout creation."""
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Asset, Order, User
from app.domains.payments.payment_gateways import (
    CheckoutResult,
    PaymentGateway,
    get_enabled_payment_methods,
    get_payment_gateways,
)
from app.shared.url_utils import InvalidRedirectURLError, validate_checkout_redirect_url

from app.domains.orders.schemas import OrderCreateRequest


def get_payment_gateway_or_raise(payment_method: str) -> PaymentGateway:
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


def get_active_asset_or_raise(db, asset_id: int) -> Asset:
    from sqlalchemy.orm import Session
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.is_active.is_(True),
        Asset.status == "active",
    ).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


def remaining_special_fractions(asset: Asset) -> int:
    return max(0, asset.special_price_fractions_cap - (asset.sold_special_fractions or 0))


def validate_fraction_count_or_raise(fraction_count: int, asset: Asset) -> None:
    remaining = remaining_special_fractions(asset)
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


def resolve_checkout_urls(body: OrderCreateRequest, gateway: PaymentGateway) -> tuple[str, str]:
    success_url = body.return_url or gateway.success_url
    cancel_url = body.cancel_url or gateway.cancel_url
    if body.return_url:
        success_url = validate_checkout_redirect_url(body.return_url, "return_url")
    if body.cancel_url:
        cancel_url = validate_checkout_redirect_url(body.cancel_url, "cancel_url")
    return success_url, cancel_url


def calculate_amount_eur_cents(asset: Asset, fraction_count: int) -> int:
    price_special_decimal = Decimal(str(asset.price_special_eur))
    return int(price_special_decimal * Decimal("100") * Decimal(str(fraction_count)))


def create_pending_order(
    db,
    *,
    current_user: User,
    asset: Asset,
    fraction_count: int,
    amount_eur_cents: int,
    payment_method: str,
) -> Order:
    order = Order(
        user_id=current_user.id,
        asset_id=asset.id,
        fraction_count=fraction_count,
        amount_eur_cents=amount_eur_cents,
        payment_method=payment_method,
        status="pending",
    )
    db.add(order)
    db.flush()
    return order


def create_checkout_or_raise(
    db: Session,
    *,
    gateway: PaymentGateway,
    order: Order,
    asset: Asset,
    amount_eur_cents: int,
    success_url: str,
    cancel_url: str,
) -> CheckoutResult:
    try:
        result = gateway.create_checkout(
            order_id=order.id,
            amount_eur_cents=amount_eur_cents,
            fraction_count=order.fraction_count,
            asset_name=asset.name,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except InvalidRedirectURLError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
