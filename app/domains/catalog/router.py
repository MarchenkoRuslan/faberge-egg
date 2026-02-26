"""Catalog routers: showrooms and assets."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.domains.catalog.schemas import (
    AssetDetailResponse,
    AssetListResponse,
    ShowroomDetailResponse,
    ShowroomListResponse,
)
from app.domains.catalog.service import (
    asset_to_detail,
    asset_to_list,
    showroom_image_url,
)
from app.models import Asset, Showroom

showrooms_router = APIRouter()


@showrooms_router.get(
    "",
    response_model=list[ShowroomListResponse],
    summary="List active showrooms",
)
def list_showrooms(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    showrooms = (
        db.query(Showroom)
        .filter(Showroom.status == "active")
        .order_by(Showroom.sort_order)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ShowroomListResponse(
            slug=s.slug,
            name=s.name,
            headline=s.headline,
            image_url=showroom_image_url(s, "image_key"),
            background_image_url=showroom_image_url(s, "background_image_key"),
        )
        for s in showrooms
    ]


@showrooms_router.get(
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
            joinedload(Showroom.assets).joinedload(Asset.media),
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
        image_url=showroom_image_url(showroom, "image_key"),
        background_image_url=showroom_image_url(showroom, "background_image_key"),
        assets=[asset_to_detail(a) for a in active_assets],
    )


assets_router = APIRouter()


@assets_router.get(
    "",
    response_model=list[AssetListResponse],
    summary="List all active assets",
)
def list_assets(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Returns all active assets with remaining special fractions and prices."""
    assets = (
        db.query(Asset)
        .options(joinedload(Asset.media))
        .filter(Asset.is_active.is_(True), Asset.status == "active")
        .order_by(Asset.sort_order)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [asset_to_list(a) for a in assets]


@assets_router.get(
    "/{slug}",
    response_model=AssetDetailResponse,
    summary="Get asset detail",
)
def get_asset(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
):
    asset = (
        db.query(Asset)
        .options(joinedload(Asset.media))
        .filter(Asset.slug == slug, Asset.status == "active", Asset.is_active.is_(True))
        .first()
    )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    return asset_to_detail(asset)
