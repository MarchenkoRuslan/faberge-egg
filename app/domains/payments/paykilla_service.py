# PayKilla integration - placeholder; real implementation in paykilla todo

from app.shared.url_utils import append_query_param, validate_redirect_url


def create_payment(
    order_id: int,
    amount_eur_cents: int,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create PayKilla payment and return checkout URL. Placeholder returns success_url with order_id."""
    from app.core.config import settings

    if not settings.PAYKILLA_API_KEY:
        raise ValueError("PAYKILLA_API_KEY is not set")
    validate_redirect_url(success_url)
    validate_redirect_url(cancel_url)
    # TODO: call PayKilla API per their docs
    return append_query_param(success_url, "order_id", order_id)
