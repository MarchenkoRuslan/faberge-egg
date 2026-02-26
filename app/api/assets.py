from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.models import Asset, get_db
from app.api.showrooms import _asset_to_detail, _asset_to_list
from app.schemas.showrooms import AssetDetailResponse, AssetListResponse

router = APIRouter()


@router.get(
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
    return [_asset_to_list(a) for a in assets]


@router.get(
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
    return _asset_to_detail(asset)
