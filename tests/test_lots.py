import pytest
from fastapi import status


def test_list_lots_empty(client):
    """Test listing lots when none exist."""
    response = client.get("/api/lots")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_lots_success(client, test_lot):
    """Test listing active lots."""
    response = client.get("/api/lots")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    
    lot_data = data[0]
    assert lot_data["id"] == test_lot.id
    assert lot_data["name"] == "Test Lot"
    assert lot_data["slug"] == "test-lot"
    assert lot_data["total_fractions"] == 100_000_000
    assert lot_data["special_price_fractions_cap"] == 3_000_000
    assert lot_data["remaining_special_fractions"] == 3_000_000
    assert lot_data["is_active"] is True


def test_list_lots_excludes_inactive(client, test_lot, test_lot_inactive):
    """Test that inactive lots are not returned."""
    response = client.get("/api/lots")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == test_lot.id
    assert data[0]["is_active"] is True


def test_list_lots_remaining_calculation(client, db, test_lot):
    """Test calculation of remaining special fractions."""
    # Update lot to have some sold fractions
    test_lot.sold_special_fractions = 500_000
    db.commit()
    
    response = client.get("/api/lots")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data[0]["remaining_special_fractions"] == 2_500_000


def test_list_lots_remaining_never_negative(client, db, test_lot):
    """Test that remaining fractions never go negative."""
    # Set sold fractions higher than cap
    test_lot.sold_special_fractions = 5_000_000
    db.commit()
    
    response = client.get("/api/lots")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data[0]["remaining_special_fractions"] == 0


def test_get_lot_by_id_success(client, test_lot):
    """Test getting a lot by ID."""
    response = client.get(f"/api/lots/{test_lot.id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    assert data["id"] == test_lot.id
    assert data["name"] == "Test Lot"
    assert data["slug"] == "test-lot"
    assert data["total_fractions"] == 100_000_000
    assert data["special_price_fractions_cap"] == 3_000_000
    assert data["remaining_special_fractions"] == 3_000_000
    assert data["price_special_eur"] == "0.03"
    assert data["price_nominal_eur"] == "0.09"
    assert data["min_fractions_to_buy"] == 1
    assert data["is_active"] is True


def test_get_lot_by_id_not_found(client):
    """Test getting non-existent lot."""
    response = client.get("/api/lots/99999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_get_lot_by_id_inactive(client, test_lot_inactive):
    """Test getting inactive lot returns 404."""
    response = client.get(f"/api/lots/{test_lot_inactive.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


def test_get_lot_remaining_calculation(client, db, test_lot):
    """Test remaining fractions calculation in get lot."""
    test_lot.sold_special_fractions = 1_000_000
    db.commit()
    
    response = client.get(f"/api/lots/{test_lot.id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["remaining_special_fractions"] == 2_000_000


def test_get_lot_all_fields(client, test_lot):
    """Test that all required fields are present in response."""
    response = client.get(f"/api/lots/{test_lot.id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    
    required_fields = [
        "id",
        "name",
        "slug",
        "total_fractions",
        "special_price_fractions_cap",
        "remaining_special_fractions",
        "price_special_eur",
        "price_nominal_eur",
        "min_fractions_to_buy",
        "is_active",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
