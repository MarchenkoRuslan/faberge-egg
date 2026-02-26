from decimal import Decimal
from unittest.mock import patch

from fastapi import status

from app.models.asset import Asset
from app.models.asset_media import AssetMedia
from app.models.showroom import Showroom


def _create_showroom(db, slug="test-showroom", name="Test Showroom", **kwargs):
    defaults = dict(
        slug=slug,
        name=name,
        headline="Test headline",
        description="Test description",
        status="active",
        sort_order=0,
    )
    defaults.update(kwargs)
    showroom = Showroom(**defaults)
    db.add(showroom)
    db.commit()
    db.refresh(showroom)
    return showroom


def _create_asset(db, showroom, slug="test-asset", name="Test Asset", **kwargs):
    defaults = dict(
        showroom_id=showroom.id,
        slug=slug,
        name=name,
        headline="Asset headline",
        description="Asset description",
        meta={"origin": "Test"},
        status="active",
        sort_order=0,
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=Decimal("0.03"),
        price_nominal_eur=Decimal("0.09"),
        sold_special_fractions=0,
        is_active=True,
    )
    defaults.update(kwargs)
    asset = Asset(**defaults)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _create_media(db, asset, kind="hero", storage_key="test/hero.jpg", **kwargs):
    defaults = dict(
        asset_id=asset.id,
        kind=kind,
        media_type="image/jpeg",
        storage_key=storage_key,
        filename="hero.jpg",
        alt_text="Test image",
        sort_order=0,
    )
    defaults.update(kwargs)
    media = AssetMedia(**defaults)
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


# --- Showroom list ---


def test_list_showrooms_empty(client):
    response = client.get("/api/showrooms")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_showrooms_returns_active(client, db):
    _create_showroom(db, slug="active-one", status="active")
    _create_showroom(db, slug="draft-one", status="draft")

    response = client.get("/api/showrooms")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["slug"] == "active-one"


def test_list_showrooms_fields(client, db):
    _create_showroom(db, slug="s1", name="Showroom One", headline="Headline 1")

    response = client.get("/api/showrooms")
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["slug"] == "s1"
    assert item["name"] == "Showroom One"
    assert item["headline"] == "Headline 1"


def test_list_showrooms_sorted(client, db):
    _create_showroom(db, slug="second", sort_order=2)
    _create_showroom(db, slug="first", sort_order=1)

    response = client.get("/api/showrooms")
    slugs = [s["slug"] for s in response.json()]
    assert slugs == ["first", "second"]


# --- Showroom detail ---


def test_get_showroom_not_found(client):
    response = client.get("/api/showrooms/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_showroom_draft_returns_404(client, db):
    _create_showroom(db, slug="hidden", status="draft")
    response = client.get("/api/showrooms/hidden")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_showroom_with_assets(mock_presign, client, db):
    showroom = _create_showroom(db)
    asset = _create_asset(db, showroom)
    _create_media(db, asset)

    response = client.get(f"/api/showrooms/{showroom.slug}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["slug"] == showroom.slug
    assert data["name"] == showroom.name
    assert len(data["assets"]) == 1

    asset_data = data["assets"][0]
    assert asset_data["slug"] == "test-asset"
    assert len(asset_data["media"]) == 1
    assert asset_data["media"][0]["url"] == "https://signed.example.com/img.jpg"
    assert asset_data["total_fractions"] == 100_000_000
    assert asset_data["price_special_eur"] == "0.03"


@patch("app.domains.catalog.service.get_presigned_url", return_value=None)
def test_get_showroom_media_url_none_when_s3_unavailable(mock_presign, client, db):
    showroom = _create_showroom(db)
    asset = _create_asset(db, showroom)
    _create_media(db, asset)

    response = client.get(f"/api/showrooms/{showroom.slug}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["assets"][0]["media"][0]["url"] is None


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_showroom_image_urls_from_meta(mock_presign, client, db):
    _create_showroom(
        db,
        meta={
            "image_key": "sr/image.jpg",
            "background_image_key": "sr/bg.jpg",
        },
    )
    response = client.get("/api/showrooms")
    item = response.json()[0]
    assert item["image_url"] == "https://signed.example.com/img.jpg"
    assert item["background_image_url"] == "https://signed.example.com/img.jpg"

    detail = client.get(f"/api/showrooms/{item['slug']}").json()
    assert detail["image_url"] == "https://signed.example.com/img.jpg"
    assert detail["background_image_url"] == "https://signed.example.com/img.jpg"


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_showroom_image_urls_none_without_meta(mock_presign, client, db):
    _create_showroom(db)
    response = client.get("/api/showrooms")
    item = response.json()[0]
    assert item["image_url"] is None
    assert item["background_image_url"] is None


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_showroom_excludes_draft_assets(mock_presign, client, db):
    showroom = _create_showroom(db)
    _create_asset(db, showroom, slug="active-asset", status="active")
    _create_asset(db, showroom, slug="draft-asset", status="draft")

    response = client.get(f"/api/showrooms/{showroom.slug}")
    assets = response.json()["assets"]
    assert len(assets) == 1
    assert assets[0]["slug"] == "active-asset"


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_showroom_asset_without_commerce(mock_presign, client, db):
    showroom = _create_showroom(db)
    _create_asset(db, showroom, total_fractions=0, is_active=True)

    response = client.get(f"/api/showrooms/{showroom.slug}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["assets"][0]["total_fractions"] == 0


# --- Asset detail ---


@patch("app.domains.catalog.service.get_presigned_url", return_value="https://signed.example.com/img.jpg")
def test_get_asset_detail(mock_presign, client, db):
    showroom = _create_showroom(db)
    asset = _create_asset(db, showroom)
    _create_media(db, asset, kind="hero", storage_key="test/hero.jpg", sort_order=0)
    _create_media(db, asset, kind="gallery", storage_key="test/gallery.jpg", sort_order=1)

    response = client.get(f"/api/assets/{asset.slug}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["slug"] == "test-asset"
    assert data["meta"] == {"origin": "Test"}
    assert len(data["media"]) == 2
    assert data["media"][0]["kind"] == "hero"
    assert data["media"][1]["kind"] == "gallery"
    assert data["price_special_eur"] == "0.03"
    assert data["total_fractions"] == 100_000_000


def test_get_asset_not_found(client):
    response = client.get("/api/assets/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_asset_draft_returns_404(client, db):
    showroom = _create_showroom(db)
    _create_asset(db, showroom, slug="hidden-asset", status="draft")

    response = client.get("/api/assets/hidden-asset")
    assert response.status_code == status.HTTP_404_NOT_FOUND
