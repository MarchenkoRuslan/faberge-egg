import json
from unittest.mock import patch

import pytest
import stripe
from fastapi import status

from app.models.lot import Lot
from app.models.order import Order


def test_stripe_webhook_success(client, test_user, test_lot, db):
    """Test successful Stripe webhook processing."""
    # Create an order
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="pending",
    )
    db.add(order)
    db.commit()
    order_id = order.id
    
    # Create Stripe event payload
    event_data = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["received"] is True
        
        # Verify order was updated
        db.refresh(order)
        assert order.status == "paid"
        assert order.external_payment_id == "cs_test_123"
        
        # Verify lot fractions were incremented
        db.refresh(test_lot)
        assert test_lot.sold_special_fractions == 1000


def test_stripe_webhook_idempotent(client, test_user, test_lot, db):
    """Test that Stripe webhook is idempotent (no double spend)."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="paid",  # Already paid
    )
    db.add(order)
    db.commit()
    initial_sold = test_lot.sold_special_fractions
    order_id = order.id
    
    event_data = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify fractions were not incremented again
        db.refresh(test_lot)
        assert test_lot.sold_special_fractions == initial_sold


def test_stripe_webhook_invalid_signature(client):
    """Test Stripe webhook with invalid signature."""
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "sig")
        
        response = client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "invalid"},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "signature" in response.json()["detail"].lower()


def test_stripe_webhook_invalid_payload(client):
    """Test Stripe webhook with invalid payload."""
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.side_effect = ValueError("Invalid payload")
        
        response = client.post(
            "/webhooks/stripe",
            content=b"invalid json",
            headers={"stripe-signature": "test"},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_stripe_webhook_no_order_id(client):
    """Test Stripe webhook without order_id in metadata."""
    event_data = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "metadata": {},
            }
        },
    }
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["received"] is True


def test_stripe_webhook_order_not_found(client):
    """Test Stripe webhook with non-existent order."""
    event_data = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "metadata": {"order_id": "99999"},
            }
        },
    }
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        
        assert response.status_code == status.HTTP_200_OK


def test_stripe_webhook_other_event_type(client):
    """Test Stripe webhook with other event type (should be ignored)."""
    event_data = {
        "id": "evt_test",
        "type": "payment_intent.succeeded",
        "data": {"object": {}},
    }
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        
        assert response.status_code == status.HTTP_200_OK


def test_stripe_webhook_no_secret(client):
    """Test Stripe webhook when webhook secret is not set."""
    import os
    original_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    os.environ["STRIPE_WEBHOOK_SECRET"] = ""
    
    try:
        response = client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "test"},
        )
        assert response.status_code == status.HTTP_200_OK
    finally:
        if original_secret:
            os.environ["STRIPE_WEBHOOK_SECRET"] = original_secret


import hashlib
import hmac

def _paykilla_post(client, payload: dict, *, include_signature: bool = True, secret: str = "pk_whsec_test_mock"):
    raw_body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if include_signature:
        signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        headers["x-paykilla-signature"] = signature
    return client.post("/webhooks/paykilla", content=raw_body, headers=headers)


def test_paykilla_webhook_success(client, test_user, test_lot, db):
    """Test successful PayKilla webhook processing."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="pending",
    )
    db.add(order)
    db.commit()
    order_id = order.id

    response = _paykilla_post(
        client,
        {
            "order_id": order_id,
            "transaction_id": "tx_paykilla_123",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["received"] is True

    db.refresh(order)
    assert order.status == "paid"
    assert order.external_payment_id == "tx_paykilla_123"

    db.refresh(test_lot)
    assert test_lot.sold_special_fractions == 500


def test_paykilla_webhook_idempotent(client, test_user, test_lot, db):
    """Test that PayKilla webhook is idempotent."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="paid",
    )
    db.add(order)
    db.commit()
    initial_sold = test_lot.sold_special_fractions
    order_id = order.id

    response = _paykilla_post(
        client,
        {
            "order_id": order_id,
            "transaction_id": "tx_paykilla_123",
        },
    )

    assert response.status_code == status.HTTP_200_OK

    db.refresh(test_lot)
    assert test_lot.sold_special_fractions == initial_sold


def test_paykilla_webhook_missing_signature(client):
    response = _paykilla_post(client, {"order_id": 1}, include_signature=False)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_paykilla_webhook_invalid_signature(client):
    response = _paykilla_post(client, {"order_id": 1}, secret="wrong-secret")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_paykilla_webhook_no_order_id(client):
    """Test PayKilla webhook without order_id."""
    response = _paykilla_post(client, {})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "order_id" in response.json()["detail"].lower()


def test_paykilla_webhook_invalid_json(client):
    """Test PayKilla webhook with invalid JSON."""
    raw_body = b"invalid json"
    signature = hmac.new(b"pk_whsec_test_mock", raw_body, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/paykilla",
        content=raw_body,
        headers={"Content-Type": "application/json", "x-paykilla-signature": signature},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_paykilla_webhook_invalid_order_id_format(client):
    """Test PayKilla webhook with invalid order_id format."""
    response = _paykilla_post(client, {"order_id": "not-a-number"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_paykilla_webhook_order_not_found(client):
    """Test PayKilla webhook with non-existent order."""
    response = _paykilla_post(client, {"order_id": 99999})

    assert response.status_code == status.HTTP_200_OK


def test_paykilla_webhook_wrong_payment_method(client, test_user, test_lot, db):
    """Test PayKilla webhook with order that has different payment method."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="stripe",
        status="pending",
    )
    db.add(order)
    db.commit()
    order_id = order.id

    response = _paykilla_post(client, {"order_id": order_id})

    assert response.status_code == status.HTTP_200_OK

    db.refresh(order)
    assert order.status == "pending"


def test_paykilla_webhook_ignores_non_success_status(client, test_user, test_lot, db):
    """Test that PayKilla webhook does not mark order as paid for failed statuses."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="pending",
    )
    db.add(order)
    db.commit()

    response = _paykilla_post(
        client,
        {
            "order_id": order.id,
            "status": "failed",
            "transaction_id": "tx_paykilla_failed_1",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["received"] is True

    db.refresh(order)
    db.refresh(test_lot)
    assert order.status == "pending"
    assert order.external_payment_id is None
    assert test_lot.sold_special_fractions == 0



def test_paykilla_webhook_amount_mismatch_keeps_order_pending(client, test_user, test_lot, db):
    """PayKilla amount mismatch must not mark order paid."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="pending",
    )
    db.add(order)
    db.commit()

    response = _paykilla_post(
        client,
        {
            "order_id": order.id,
            "amount_eur_cents": 999,
            "transaction_id": "tx_mismatch",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    db.refresh(order)
    db.refresh(test_lot)
    assert order.status == "pending"
    assert order.external_payment_id is None
    assert test_lot.sold_special_fractions == 0


def test_paykilla_webhook_capacity_exceeded_keeps_order_pending(client, test_user, test_lot, db):
    """When lot cap is exhausted, webhook must not move order to paid."""
    test_lot.sold_special_fractions = test_lot.special_price_fractions_cap
    db.commit()

    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1,
        amount_eur_cents=3,
        payment_method="paykilla",
        status="pending",
    )
    db.add(order)
    db.commit()

    response = _paykilla_post(
        client,
        {
            "order_id": order.id,
            "transaction_id": "tx_over_cap",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    db.refresh(order)
    db.refresh(test_lot)
    assert order.status == "pending"
    assert order.external_payment_id is None
    assert test_lot.sold_special_fractions == test_lot.special_price_fractions_cap


def test_stripe_webhook_non_positive_order_id(client):
    """Stripe webhook should ignore non-positive order_id."""
    event_data = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_123", "metadata": {"order_id": "0"}}},
    }

    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = event_data
        response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["received"] is True



def test_paykilla_webhook_non_positive_amount_returns_400(client, test_user, test_lot, db):
    """amount_eur_cents must be a positive integer when provided."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="pending",
    )
    db.add(order)
    db.commit()

    response = _paykilla_post(
        client,
        {
            "order_id": order.id,
            "amount_eur_cents": 0,
            "transaction_id": "tx_zero_amount",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "amount_eur_cents" in response.json()["detail"]

    db.refresh(order)
    assert order.status == "pending"
    assert order.external_payment_id is None


def test_paykilla_webhook_non_positive_order_id_with_valid_signature(client):
    """PayKilla callback should return 400 for non-positive order_id with valid signature."""
    from app.config import settings
    import hmac
    import hashlib

    payload = json.dumps({"order_id": 0}).encode()
    signature = hmac.new(
        settings.PAYKILLA_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    response = client.post(
        "/webhooks/paykilla",
        content=payload,
        headers={"x-paykilla-signature": signature},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "positive" in response.json()["detail"]
