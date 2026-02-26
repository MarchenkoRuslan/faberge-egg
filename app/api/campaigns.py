"""Admin endpoints for monitoring and managing upsale email campaigns.

Mounted at ``/api/admin/campaigns``.  All endpoints require JWT auth.

- ``GET  /campaigns``             -- list campaigns (filter by status, user_id)
- ``GET  /campaigns/{id}``        -- campaign detail with email log
- ``POST /campaigns/{id}/cancel`` -- cancel an active campaign
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.models import User, get_db
from app.models.upsale_campaign import UpsaleCampaign
from app.schemas.campaigns import (
    CampaignDetailResponse,
    CampaignResponse,
)

router = APIRouter()


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
    campaign_status: Annotated[str | None, Query(alias="status")] = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    query = db.query(UpsaleCampaign)
    if campaign_status:
        query = query.filter(UpsaleCampaign.status == campaign_status)
    if user_id is not None:
        query = query.filter(UpsaleCampaign.user_id == user_id)
    query = query.order_by(UpsaleCampaign.created_at.desc())
    return query.offset(offset).limit(limit).all()


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailResponse)
def get_campaign(
    campaign_id: int,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
):
    campaign = db.query(UpsaleCampaign).filter(UpsaleCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return campaign


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel_campaign(
    campaign_id: int,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
):
    campaign = db.query(UpsaleCampaign).filter(UpsaleCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    if campaign.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campaign is already {campaign.status}",
        )
    campaign.status = "cancelled"
    campaign.step = "completed"
    db.commit()
    db.refresh(campaign)
    return campaign
