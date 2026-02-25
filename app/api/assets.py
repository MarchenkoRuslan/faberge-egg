from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models import Asset, get_db
from app.api.showrooms import _asset_to_detail
from app.schemas.showrooms import AssetDetailResponse

router = APIRouter()


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
        .options(
            joinedload(Asset.media),
            joinedload(Asset.lots),
        )
        .filter(Asset.slug == slug, Asset.status == "active")
        .first()
    )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    return _asset_to_detail(asset)
