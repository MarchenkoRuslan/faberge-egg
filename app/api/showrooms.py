from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Asset, Showroom, get_db
from app.schemas.showrooms import (
    AssetDetailResponse,
    AssetLotResponse,
    AssetMediaResponse,
    ShowroomDetailResponse,
    ShowroomListResponse,
)
from app.services.storage import get_presigned_url

router = APIRouter()


def _media_to_response(media) -> AssetMediaResponse:
    url = get_presigned_url(media.storage_key)
    return AssetMediaResponse(
        kind=media.kind,
        media_type=media.media_type,
        url=url,
        filename=media.filename,
        alt_text=media.alt_text,
    )


def _lot_to_response(lot) -> AssetLotResponse:
    remaining = max(0, lot.special_price_fractions_cap - lot.sold_special_fractions)
    return AssetLotResponse(
        id=lot.id,
        slug=lot.slug,
        total_fractions=lot.total_fractions,
        special_price_fractions_cap=lot.special_price_fractions_cap,
        remaining_special_fractions=remaining,
        price_special_eur=lot.price_special_eur,
        price_nominal_eur=lot.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=lot.is_active,
    )


def _asset_to_detail(asset: Asset) -> AssetDetailResponse:
    media_list = [_media_to_response(m) for m in asset.media]
    active_lots = [lot for lot in asset.lots if lot.is_active]
    lot_response = _lot_to_response(active_lots[0]) if active_lots else None

    return AssetDetailResponse(
        slug=asset.slug,
        name=asset.name,
        headline=asset.headline,
        description=asset.description,
        meta=asset.meta,
        media=media_list,
        lot=lot_response,
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
            joinedload(Showroom.assets)
            .joinedload(Asset.lots),
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
        [a for a in showroom.assets if a.status == "active"],
        key=lambda a: a.sort_order,
    )

    return ShowroomDetailResponse(
        slug=showroom.slug,
        name=showroom.name,
        headline=showroom.headline,
        description=showroom.description,
        meta=showroom.meta,
        assets=[_asset_to_detail(a) for a in active_assets],
    )
