"""Admin endpoints for monitoring and managing upsale email campaigns."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_admin_user
from app.models import User
from app.models.upsale_campaign import UpsaleCampaign
from app.domains.campaigns.schemas import CampaignDetailResponse, CampaignResponse

router = APIRouter()


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_admin_user)],
    campaign_status: Annotated[str | None, Query(alias="status")] = None,
    user_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
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
    _user: Annotated[User, Depends(get_admin_user)],
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
    _user: Annotated[User, Depends(get_admin_user)],
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
