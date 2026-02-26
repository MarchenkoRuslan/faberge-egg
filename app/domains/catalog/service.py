"""Catalog mapping: Asset/Showroom models to API response schemas."""
from app.core.config import settings
from app.models import Asset
from app.models.showroom import Showroom
from app.shared.storage import get_presigned_url

from app.domains.catalog.schemas import (
    AssetDetailResponse,
    AssetListResponse,
    AssetMediaResponse,
)


def showroom_image_url(showroom: Showroom, key_name: str) -> str | None:
    meta = showroom.meta or {}
    storage_key = meta.get(key_name)
    if not storage_key:
        return None
    return get_presigned_url(storage_key)


def media_to_response(media) -> AssetMediaResponse:
    url = get_presigned_url(media.storage_key)
    return AssetMediaResponse(
        kind=media.kind,
        media_type=media.media_type,
        url=url,
        filename=media.filename,
        alt_text=media.alt_text,
    )


def remaining_special(asset: Asset) -> int:
    return max(0, asset.special_price_fractions_cap - (asset.sold_special_fractions or 0))


def asset_to_list(asset: Asset) -> AssetListResponse:
    hero = next((m for m in asset.media if m.kind == "hero"), None)
    return AssetListResponse(
        id=asset.id,
        slug=asset.slug,
        name=asset.name,
        headline=asset.headline,
        hero_image=media_to_response(hero) if hero else None,
        total_fractions=asset.total_fractions,
        special_price_fractions_cap=asset.special_price_fractions_cap,
        remaining_special_fractions=remaining_special(asset),
        price_special_eur=asset.price_special_eur,
        price_nominal_eur=asset.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=asset.is_active,
    )


def asset_to_detail(asset: Asset) -> AssetDetailResponse:
    media_list = [media_to_response(m) for m in asset.media]
    return AssetDetailResponse(
        id=asset.id,
        slug=asset.slug,
        name=asset.name,
        headline=asset.headline,
        description=asset.description,
        meta=asset.meta,
        media=media_list,
        total_fractions=asset.total_fractions,
        special_price_fractions_cap=asset.special_price_fractions_cap,
        remaining_special_fractions=remaining_special(asset),
        price_special_eur=asset.price_special_eur,
        price_nominal_eur=asset.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=asset.is_active,
    )
