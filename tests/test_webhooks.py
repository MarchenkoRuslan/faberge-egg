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
    
    response = client.post(
        "/webhooks/paykilla",
        json={
            "order_id": order_id,
            "transaction_id": "tx_paykilla_123",
        },
    )
    
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["received"] is True
    
    # Verify order was updated
    db.refresh(order)
    assert order.status == "paid"
    assert order.external_payment_id == "tx_paykilla_123"
    
    # Verify lot fractions were incremented
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
    
    response = client.post(
        "/webhooks/paykilla",
        json={
            "order_id": order_id,
            "transaction_id": "tx_paykilla_123",
        },
    )
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify fractions were not incremented again
    db.refresh(test_lot)
    assert test_lot.sold_special_fractions == initial_sold


def test_paykilla_webhook_no_order_id(client):
    """Test PayKilla webhook without order_id."""
    response = client.post(
        "/webhooks/paykilla",
        json={},
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "order_id" in response.json()["detail"].lower()


def test_paykilla_webhook_invalid_json(client):
    """Test PayKilla webhook with invalid JSON."""
    response = client.post(
        "/webhooks/paykilla",
        content=b"invalid json",
        headers={"Content-Type": "application/json"},
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_paykilla_webhook_invalid_order_id_format(client):
    """Test PayKilla webhook with invalid order_id format."""
    response = client.post(
        "/webhooks/paykilla",
        json={"order_id": "not-a-number"},
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_paykilla_webhook_order_not_found(client):
    """Test PayKilla webhook with non-existent order."""
    response = client.post(
        "/webhooks/paykilla",
        json={"order_id": 99999},
    )
    
    assert response.status_code == status.HTTP_200_OK


def test_paykilla_webhook_wrong_payment_method(client, test_user, test_lot, db):
    """Test PayKilla webhook with order that has different payment method."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="stripe",  # Not paykilla
        status="pending",
    )
    db.add(order)
    db.commit()
    order_id = order.id
    
    response = client.post(
        "/webhooks/paykilla",
        json={"order_id": order_id},
    )
    
    assert response.status_code == status.HTTP_200_OK
    
    # Order should not be updated
    db.refresh(order)
    assert order.status == "pending"
