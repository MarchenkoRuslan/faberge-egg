from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Asset, Showroom, get_db
from app.schemas.showrooms import (
    AssetDetailResponse,
    AssetListResponse,
    AssetMediaResponse,
    ShowroomDetailResponse,
    ShowroomListResponse,
)
from app.services.storage import get_presigned_url

router = APIRouter()


def _showroom_image_url(showroom: Showroom, key_name: str) -> str | None:
    meta = showroom.meta or {}
    storage_key = meta.get(key_name)
    if not storage_key:
        return None
    return get_presigned_url(storage_key)


def _media_to_response(media) -> AssetMediaResponse:
    url = get_presigned_url(media.storage_key)
    return AssetMediaResponse(
        kind=media.kind,
        media_type=media.media_type,
        url=url,
        filename=media.filename,
        alt_text=media.alt_text,
    )


def _remaining_special(asset: Asset) -> int:
    return max(0, asset.special_price_fractions_cap - asset.sold_special_fractions)


def _asset_to_list(asset: Asset) -> AssetListResponse:
    hero = next((m for m in asset.media if m.kind == "hero"), None)
    return AssetListResponse(
        id=asset.id,
        slug=asset.slug,
        name=asset.name,
        headline=asset.headline,
        hero_image=_media_to_response(hero) if hero else None,
        total_fractions=asset.total_fractions,
        special_price_fractions_cap=asset.special_price_fractions_cap,
        remaining_special_fractions=_remaining_special(asset),
        price_special_eur=asset.price_special_eur,
        price_nominal_eur=asset.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=asset.is_active,
    )


def _asset_to_detail(asset: Asset) -> AssetDetailResponse:
    media_list = [_media_to_response(m) for m in asset.media]
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
        remaining_special_fractions=_remaining_special(asset),
        price_special_eur=asset.price_special_eur,
        price_nominal_eur=asset.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=asset.is_active,
    )


@router.get(
    "",
    response_model=list[ShowroomListResponse],
    summary="List active showrooms",
)
def list_showrooms(
    db: Annotated[Session, Depends(get_db)],
):
    showrooms = (
        db.query(Showroom)
        .filter(Showroom.status == "active")
        .order_by(Showroom.sort_order)
        .all()
    )
    return [
        ShowroomListResponse(
            slug=s.slug,
            name=s.name,
            headline=s.headline,
            image_url=_showroom_image_url(s, "image_key"),
            background_image_url=_showroom_image_url(s, "background_image_key"),
        )
        for s in showrooms
    ]


@router.get(
    "/{slug}",
    response_model=ShowroomDetailResponse,
    summary="Get showroom detail with assets",
)
def get_showroom(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
):
    showroom = (
        db.query(Showroom)
        .options(
            joinedload(Showroom.assets)
            .joinedload(Asset.media),
        )
        .filter(Showroom.slug == slug, Showroom.status == "active")
        .first()
    )
    if not showroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Showroom not found",
        )

    active_assets = sorted(
        [a for a in showroom.assets if a.status == "active" and a.is_active],
        key=lambda a: a.sort_order,
    )

    return ShowroomDetailResponse(
        slug=showroom.slug,
        name=showroom.name,
        headline=showroom.headline,
        description=showroom.description,
        meta=showroom.meta,
        image_url=_showroom_image_url(showroom, "image_key"),
        background_image_url=_showroom_image_url(showroom, "background_image_key"),
        assets=[_asset_to_detail(a) for a in active_assets],
    )
