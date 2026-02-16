from unittest.mock import MagicMock, patch

import pytest

from app.services import paykilla_service, stripe_service


def test_stripe_create_checkout_session_success():
    """Test successful Stripe checkout session creation."""
    with patch("app.services.stripe_service.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session
        
        url, session_id = stripe_service.create_checkout_session(
            order_id=1,
            amount_eur_cents=3000,
            fraction_count=1000,
            lot_name="Test Lot",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        
        assert url == "https://checkout.stripe.com/test"
        assert session_id == "cs_test_123"
        
        # Verify Stripe API was called with correct parameters
        mock_stripe.checkout.Session.create.assert_called_once()
        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs["mode"] == "payment"
        assert "metadata" in call_kwargs
        assert call_kwargs["metadata"]["order_id"] == "1"


def test_stripe_create_checkout_session_no_secret():
    """Test Stripe service error when secret key is not set."""
    import os
    original_key = os.environ.get("STRIPE_SECRET_KEY")
    os.environ["STRIPE_SECRET_KEY"] = ""
    
    try:
        with pytest.raises(ValueError, match="STRIPE_SECRET_KEY"):
            stripe_service.create_checkout_session(
                order_id=1,
                amount_eur_cents=3000,
                fraction_count=1000,
                lot_name="Test Lot",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
    finally:
        if original_key:
            os.environ["STRIPE_SECRET_KEY"] = original_key


def test_stripe_create_checkout_session_parameters():
    """Test that correct parameters are passed to Stripe API."""
    with patch("app.services.stripe_service.stripe") as mock_stripe:
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session
        
        stripe_service.create_checkout_session(
            order_id=42,
            amount_eur_cents=5000,
            fraction_count=2000,
            lot_name="Special Lot",
            success_url="https://custom.com/success",
            cancel_url="https://custom.com/cancel",
        )
        
        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        
        # Check line items
        assert len(call_kwargs["line_items"]) == 1
        line_item = call_kwargs["line_items"][0]
        assert line_item["price_data"]["currency"] == "eur"
        assert line_item["price_data"]["unit_amount"] == 5000
        assert "Special Lot" in line_item["price_data"]["product_data"]["name"]
        assert "2000" in line_item["price_data"]["product_data"]["name"]
        
        # Check URLs
        assert "order_id=42" in call_kwargs["success_url"]
        assert call_kwargs["cancel_url"] == "https://custom.com/cancel"
        
        # Check metadata
        assert call_kwargs["metadata"]["order_id"] == "42"


def test_paykilla_create_payment_success():
    """Test successful PayKilla payment creation."""
    url = paykilla_service.create_payment(
        order_id=1,
        amount_eur_cents=3000,
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    
    assert url is not None
    assert "order_id=1" in url
    assert "example.com/success" in url


def test_paykilla_create_payment_no_api_key():
    """Test PayKilla service error when API key is not set."""
    import os
    original_key = os.environ.get("PAYKILLA_API_KEY")
    os.environ["PAYKILLA_API_KEY"] = ""
    
    try:
        with pytest.raises(ValueError, match="PAYKILLA_API_KEY"):
            paykilla_service.create_payment(
                order_id=1,
                amount_eur_cents=3000,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
    finally:
        if original_key:
            os.environ["PAYKILLA_API_KEY"] = original_key


def test_paykilla_create_payment_returns_url():
    """Test that PayKilla service returns a URL."""
    url = paykilla_service.create_payment(
        order_id=123,
        amount_eur_cents=5000,
        success_url="https://custom.com/success?param=value",
        cancel_url="https://custom.com/cancel",
    )
    
    assert isinstance(url, str)
    assert "order_id=123" in url
    assert "custom.com" in url
