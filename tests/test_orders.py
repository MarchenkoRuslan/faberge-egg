from unittest.mock import patch

import pytest
from fastapi import status

from app.models.order import Order


def test_create_order_stripe_success(client, test_user, test_lot, auth_headers, db):
    """Test successful order creation with Stripe."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 1000,
                "payment_method": "stripe",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "order_id" in data
        assert data["checkout_url"] == "https://checkout.stripe.com/test"
        assert data["session_id"] == "cs_test_123"
        assert data["payment_method"] == "stripe"
        
        # Verify order was created
        order = db.query(Order).filter(Order.id == data["order_id"]).first()
        assert order is not None
        assert order.user_id == test_user.id
        assert order.lot_id == test_lot.id
        assert order.fraction_count == 1000
        assert order.payment_method == "stripe"
        assert order.status == "pending"


def test_create_order_paykilla_success(client, test_user, test_lot, auth_headers):
    """Test successful order creation with PayKilla."""
    with patch("app.services.paykilla_service.create_payment") as mock_paykilla:
        mock_paykilla.return_value = "https://paykilla.com/checkout?order_id=1"
        
        response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 500,
                "payment_method": "paykilla",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "order_id" in data
        assert "checkout_url" in data
        assert data["payment_method"] == "paykilla"


def test_create_order_min_fractions_validation(client, test_lot, auth_headers):
    """Test validation of minimum fractions."""
    response = client.post(
        "/api/orders",
        json={
            "lot_id": test_lot.id,
            "fraction_count": 0,
            "payment_method": "stripe",
        },
        headers=auth_headers,
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "minimum" in response.json()["detail"].lower()


def test_create_order_max_fractions_validation(client, test_lot, auth_headers):
    """Test validation of maximum fractions (remaining)."""
    response = client.post(
        "/api/orders",
        json={
            "lot_id": test_lot.id,
            "fraction_count": 5_000_000,  # More than available
            "payment_method": "stripe",
        },
        headers=auth_headers,
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "available" in response.json()["detail"].lower() or "only" in response.json()["detail"].lower()


def test_create_order_lot_not_found(client, auth_headers):
    """Test order creation with non-existent lot."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        response = client.post(
            "/api/orders",
            json={
                "lot_id": 99999,
                "fraction_count": 1000,
                "payment_method": "stripe",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()


def test_create_order_inactive_lot(client, test_lot_inactive, auth_headers):
    """Test order creation with inactive lot."""
    response = client.post(
        "/api/orders",
        json={
            "lot_id": test_lot_inactive.id,
            "fraction_count": 1000,
            "payment_method": "stripe",
        },
        headers=auth_headers,
    )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_order_unauthorized(client, test_lot):
    """Test order creation without authentication."""
    response = client.post(
        "/api/orders",
        json={
            "lot_id": test_lot.id,
            "fraction_count": 1000,
            "payment_method": "stripe",
        },
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_order_price_calculation(client, test_lot, auth_headers, db):
    """Test price calculation with Decimal precision."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        fraction_count = 1000
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
        
        # Price should be 0.03 * 100 * 1000 = 3000 cents
        expected_cents = int(0.03 * 100 * 1000)
        order = db.query(Order).filter(Order.id == response.json()["order_id"]).first()
        assert order.amount_eur_cents == expected_cents


def test_create_order_custom_urls(client, test_lot, auth_headers):
    """Test order creation with custom return_url and cancel_url."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.return_value.url = "https://checkout.stripe.com/test"
        mock_stripe.return_value.id = "cs_test_123"
        
        response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 1000,
                "payment_method": "stripe",
                "return_url": "https://custom.com/success",
                "cancel_url": "https://custom.com/cancel",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        # Verify Stripe was called with custom URLs
        call_args = mock_stripe.call_args
        assert "custom.com/success" in call_args[1]["success_url"]
        assert "custom.com/cancel" in call_args[1]["cancel_url"]


def test_create_order_stripe_error(client, test_lot, auth_headers):
    """Test order creation when Stripe service fails."""
    with patch("app.services.stripe_service.stripe.checkout.Session.create") as mock_stripe:
        mock_stripe.side_effect = ValueError("Stripe API error")
        
        response = client.post(
            "/api/orders",
            json={
                "lot_id": test_lot.id,
                "fraction_count": 1000,
                "payment_method": "stripe",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_create_order_unsupported_payment_method(client, test_lot, auth_headers):
    """Test order creation with unsupported payment method."""
    response = client.post(
        "/api/orders",
        json={
            "lot_id": test_lot.id,
            "fraction_count": 1000,
            "payment_method": "bitcoin",
        },
        headers=auth_headers,
    )
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert any(err.get("type") == "literal_error" for err in response.json()["detail"])


def test_get_my_orders_success(client, test_user, test_lot, auth_headers, db):
    """Test getting list of user's orders."""
    # Create some orders
    order1 = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="pending",
    )
    order2 = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="paykilla",
        status="paid",
    )
    db.add(order1)
    db.add(order2)
    db.commit()
    
    response = client.get("/api/orders/me", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    
    # Check that orders belong to the user
    for order in data:
        assert order["lot_id"] == test_lot.id


def test_get_my_orders_only_current_user(client, test_user, test_user2, test_lot, auth_headers, db):
    """Test that only current user's orders are returned."""
    # Create order for test_user
    order1 = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="pending",
    )
    # Create order for test_user2
    order2 = Order(
        user_id=test_user2.id,
        lot_id=test_lot.id,
        fraction_count=500,
        amount_eur_cents=1500,
        payment_method="stripe",
        status="pending",
    )
    db.add(order1)
    db.add(order2)
    db.commit()
    
    response = client.get("/api/orders/me", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    # Should only return orders for test_user
    user_order_ids = [o["id"] for o in data if o["id"] == order1.id]
    assert len(user_order_ids) >= 1
    assert order2.id not in [o["id"] for o in data]


def test_get_my_orders_unauthorized(client):
    """Test getting orders without authentication."""
    response = client.get("/api/orders/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_order_status_success(client, test_user, test_lot, auth_headers, db):
    """Test getting order status."""
    order = Order(
        user_id=test_user.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="paid",
    )
    db.add(order)
    db.commit()
    
    response = client.get(f"/api/orders/{order.id}/status", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == order.id
    assert data["status"] == "paid"
    assert data["fraction_count"] == 1000
    assert data["amount_eur_cents"] == 3000


def test_get_order_status_not_found(client, auth_headers):
    """Test getting status of non-existent order."""
    response = client.get("/api/orders/99999/status", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_order_status_other_user(client, test_user2, test_lot, auth_headers, db):
    """Test getting status of another user's order."""
    order = Order(
        user_id=test_user2.id,
        lot_id=test_lot.id,
        fraction_count=1000,
        amount_eur_cents=3000,
        payment_method="stripe",
        status="pending",
    )
    db.add(order)
    db.commit()
    
    response = client.get(f"/api/orders/{order.id}/status", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_order_status_unauthorized(client, test_user, test_lot, db):
    """Test getting order status without authentication."""
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
    
    response = client.get(f"/api/orders/{order.id}/status")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
