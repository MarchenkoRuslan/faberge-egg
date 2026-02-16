# PayKilla integration - placeholder; real implementation in paykilla todo


def create_payment(
    order_id: int,
    amount_eur_cents: int,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create PayKilla payment and return checkout URL. Placeholder returns success_url with order_id."""
    from app.config import settings

    if not settings.PAYKILLA_API_KEY:
        raise ValueError("PAYKILLA_API_KEY is not set")
    # TODO: call PayKilla API per their docs
    return success_url + f"?order_id={order_id}"
