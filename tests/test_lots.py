from unittest.mock import patch

from fastapi import status


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_list_assets_empty(mock_presign, client):
    """Test listing assets when none exist."""
    response = client.get("/api/assets")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_list_assets_success(mock_presign, client, test_asset):
    """Test listing active assets."""
    response = client.get("/api/assets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    asset_data = data[0]
    assert asset_data["id"] == test_asset.id
    assert asset_data["name"] == "Test Asset"
    assert asset_data["slug"] == "test-asset"
    assert asset_data["total_fractions"] == 100_000_000
    assert asset_data["special_price_fractions_cap"] == 3_000_000
    assert asset_data["remaining_special_fractions"] == 3_000_000
    assert asset_data["is_active"] is True


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_list_assets_excludes_inactive(mock_presign, client, test_asset, test_asset_inactive):
    """Test that inactive assets are not returned."""
    response = client.get("/api/assets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == test_asset.id
    assert data[0]["is_active"] is True


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_list_assets_remaining_calculation(mock_presign, client, db, test_asset):
    """Test calculation of remaining special fractions."""
    test_asset.sold_special_fractions = 500_000
    db.commit()

    response = client.get("/api/assets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data[0]["remaining_special_fractions"] == 2_500_000


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_list_assets_remaining_never_negative(mock_presign, client, db, test_asset):
    """Test that remaining fractions never go negative."""
    test_asset.sold_special_fractions = 5_000_000
    db.commit()

    response = client.get("/api/assets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data[0]["remaining_special_fractions"] == 0


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_asset_by_slug_success(mock_presign, client, test_asset):
    """Test getting an asset by slug."""
    response = client.get(f"/api/assets/{test_asset.slug}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["id"] == test_asset.id
    assert data["name"] == "Test Asset"
    assert data["slug"] == "test-asset"
    assert data["total_fractions"] == 100_000_000
    assert data["special_price_fractions_cap"] == 3_000_000
    assert data["remaining_special_fractions"] == 3_000_000
    assert data["price_special_eur"] == "0.03"
    assert data["price_nominal_eur"] == "0.09"
    assert data["min_fractions_to_buy"] == 1
    assert data["is_active"] is True


def test_get_asset_by_slug_not_found(client):
    """Test getting non-existent asset."""
    response = client.get("/api/assets/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_asset_remaining_calculation(mock_presign, client, db, test_asset):
    """Test remaining fractions calculation in get asset."""
    test_asset.sold_special_fractions = 1_000_000
    db.commit()

    response = client.get(f"/api/assets/{test_asset.slug}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["remaining_special_fractions"] == 2_000_000


@patch("app.api.showrooms.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_asset_all_fields(mock_presign, client, test_asset):
    """Test that all required fields are present in response."""
    response = client.get(f"/api/assets/{test_asset.slug}")
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
