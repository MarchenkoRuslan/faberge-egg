import stripe

from app.services.url_utils import append_query_param, validate_redirect_url


def create_checkout_session(
    order_id: int,
    amount_eur_cents: int,
    fraction_count: int,
    asset_name: str,
    success_url: str,
    cancel_url: str,
) -> tuple[str, str]:
    """Create Stripe Checkout Session and return (checkout URL, session ID)."""
    from app.config import settings

    if not settings.STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY is not set")
    validate_redirect_url(success_url)
    validate_redirect_url(cancel_url)
    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"{asset_name} - {fraction_count} fraction(s)",
                    },
                    "unit_amount": amount_eur_cents,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=append_query_param(success_url, "order_id", order_id),
        cancel_url=cancel_url,
        metadata={"order_id": str(order_id)},
    )
    return session.url, session.id
