import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import status

from app.models.lot import Lot
from app.models.order import Order


def test_full_order_flow(client, db, test_lot):
    """Test complete flow: register -> login -> get lots -> create order -> webhook."""
    # 1. Register user
    register_response = client.post(
        "/api/auth/register",
        json={"email": "flowuser@example.com", "password": "password123"},
    )
    assert register_response.status_code == status.HTTP_200_OK
    user_id = register_response.json()["id"]
    
    # 2. Login and get token
    login_response = client.post(
        "/api/auth/login",
        json={"email": "flowuser@example.com", "password": "password123"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Get list of lots
    lots_response = client.get("/api/lots", headers=headers)
    assert lots_response.status_code == status.HTTP_200_OK
    lots = lots_response.json()
    assert len(lots) > 0
    assert lots[0]["id"] == test_lot.id
    
    # 4. Create order
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        order_response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 2000,
                "payment_method": "stripe",
            },
            headers=headers,
        )
        assert order_response.status_code == status.HTTP_200_OK
        order_data = order_response.json()
        order_id = order_data["order_id"]
        assert order_data["checkout_url"] == "https://checkout.stripe.com/test"
    
    # 5. Verify order was created
    order = db.query(Order).filter(Order.id == order_id).first()
    assert order is not None
    assert order.user_id == user_id
    assert order.status == "pending"
    assert order.fraction_count == 2000
    
    # 6. Simulate Stripe webhook
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
        
        webhook_response = client.post(
            "/webhooks/stripe",
            content=json.dumps(event_data).encode(),
            headers={"stripe-signature": "test_signature"},
        )
        assert webhook_response.status_code == status.HTTP_200_OK
    
    # 7. Verify order was updated
    db.refresh(order)
    assert order.status == "paid"
    assert order.external_payment_id == "cs_test_123"
    
    # 8. Verify lot fractions were incremented
    db.refresh(test_lot)
    assert test_lot.sold_special_fractions == 2000
    
    # 9. Get order status
    status_response = client.get(f"/api/orders/{order_id}/status", headers=headers)
    assert status_response.status_code == status.HTTP_200_OK
    status_data = status_response.json()
    assert status_data["status"] == "paid"
    assert status_data["fraction_count"] == 2000
    
    # 10. Get my orders
    my_orders_response = client.get("/api/orders/me", headers=headers)
    assert my_orders_response.status_code == status.HTTP_200_OK
    orders = my_orders_response.json()
    assert len(orders) >= 1
    assert any(o["id"] == order_id for o in orders)


def test_price_calculation_precision(client, db, test_lot, auth_headers):
    """Test that price calculation uses Decimal for precision."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        # Test with various fraction counts
        test_cases = [
            (1, 3),  # 0.03 * 100 * 1 = 3 cents
            (100, 300),  # 0.03 * 100 * 100 = 300 cents
            (1000, 3000),  # 0.03 * 100 * 1000 = 3000 cents
            (10000, 30000),  # 0.03 * 100 * 10000 = 30000 cents
        ]
        
        for fraction_count, expected_cents in test_cases:
            response = client.post(
                "/api/orders",
                json={
                    "lot_id": test_lot.id,
                    "fraction_count": fraction_count,
                    "payment_method": "stripe",
                },
                headers=auth_headers,
            )
            
            assert response.status_code == status.HTTP_200_OK
            order_id = response.json()["order_id"]
            
            order = db.query(Order).filter(Order.id == order_id).first()
            assert order.amount_eur_cents == expected_cents, (
                f"Expected {expected_cents} cents for {fraction_count} fractions, "
                f"got {order.amount_eur_cents}"
            )


def test_multiple_orders_same_lot(client, db, test_lot, auth_headers):
    """Test creating multiple orders for the same lot."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        # Create first order
        response1 = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 1000,
                "payment_method": "stripe",
            },
            headers=auth_headers,
        )
        assert response1.status_code == status.HTTP_200_OK
        order_id1 = response1.json()["order_id"]
        
        # Create second order
        response2 = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 500,
                "payment_method": "stripe",
            },
            headers=auth_headers,
        )
        assert response2.status_code == status.HTTP_200_OK
        order_id2 = response2.json()["order_id"]
        
        # Verify both orders exist
        order1 = db.query(Order).filter(Order.id == order_id1).first()
        order2 = db.query(Order).filter(Order.id == order_id2).first()
        assert order1 is not None
        assert order2 is not None
        
        # Process webhooks for both orders
        for order_id in [order_id1, order_id2]:
            event_data = {
                "id": f"evt_test_{order_id}",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": f"cs_test_{order_id}",
                        "metadata": {"order_id": str(order_id)},
                    }
                },
            }
            
            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.return_value = event_data
                client.post(
                    "/webhooks/stripe",
                    content=json.dumps(event_data).encode(),
                    headers={"stripe-signature": "test_signature"},
                )
        
        # Verify lot fractions were incremented correctly
        db.refresh(test_lot)
        assert test_lot.sold_special_fractions == 1500  # 1000 + 500


def test_order_flow_with_paykilla(client, db, test_lot, auth_headers):
    """Test complete flow with PayKilla payment."""
    with patch("app.services.paykilla_service.create_payment") as mock_paykilla:
        mock_paykilla.return_value = "https://paykilla.com/checkout?order_id=1"
        
        # Create order
        order_response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 750,
                "payment_method": "paykilla",
            },
            headers=auth_headers,
        )
        assert order_response.status_code == status.HTTP_200_OK
        order_id = order_response.json()["order_id"]
        
        # Simulate PayKilla webhook
        webhook_response = client.post(
            "/webhooks/paykilla",
            json={
                "order_id": order_id,
                "transaction_id": "tx_paykilla_123",
            },
        )
        assert webhook_response.status_code == status.HTTP_200_OK
        
        # Verify order was updated
        order = db.query(Order).filter(Order.id == order_id).first()
        assert order.status == "paid"
        assert order.external_payment_id == "tx_paykilla_123"
        
        # Verify lot fractions
        db.refresh(test_lot)
        assert test_lot.sold_special_fractions == 750
