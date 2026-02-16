from dataclasses import dataclass
from typing import Callable

from app.config import settings
from app.services import paykilla_service, stripe_service


@dataclass(frozen=True)
class CheckoutResult:
    checkout_url: str
    session_id: str | None = None


@dataclass(frozen=True)
class PaymentGateway:
    method: str
    create_checkout: Callable[[int, int, int, str, str, str], CheckoutResult]
    success_url: str
    cancel_url: str
    enabled: bool


def _create_stripe_checkout(
    order_id: int,
    amount_eur_cents: int,
    fraction_count: int,
    lot_name: str,
    success_url: str,
    cancel_url: str,
) -> CheckoutResult:
    checkout_url, session_id = stripe_service.create_checkout_session(
        order_id=order_id,
        amount_eur_cents=amount_eur_cents,
        fraction_count=fraction_count,
        lot_name=lot_name,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CheckoutResult(checkout_url=checkout_url, session_id=session_id)


def _create_paykilla_checkout(
    order_id: int,
    amount_eur_cents: int,
    fraction_count: int,
    lot_name: str,
    success_url: str,
    cancel_url: str,
) -> CheckoutResult:
    checkout_url = paykilla_service.create_payment(
        order_id=order_id,
        amount_eur_cents=amount_eur_cents,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CheckoutResult(checkout_url=checkout_url)


def get_payment_gateways() -> dict[str, PaymentGateway]:
    return {
        "stripe": PaymentGateway(
            method="stripe",
            create_checkout=_create_stripe_checkout,
            success_url=settings.STRIPE_SUCCESS_URL,
            cancel_url=settings.STRIPE_CANCEL_URL,
            enabled=bool(settings.STRIPE_SECRET_KEY),
        ),
        "paykilla": PaymentGateway(
            method="paykilla",
            create_checkout=_create_paykilla_checkout,
            success_url=settings.PAYKILLA_SUCCESS_URL,
            cancel_url=settings.PAYKILLA_CANCEL_URL,
            enabled=bool(settings.PAYKILLA_API_KEY),
        ),
    }


def get_enabled_payment_methods() -> list[str]:
    return [method for method, gateway in get_payment_gateways().items() if gateway.enabled]
