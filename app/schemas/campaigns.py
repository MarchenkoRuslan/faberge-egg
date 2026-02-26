from datetime import datetime

from pydantic import BaseModel


class CampaignEmailLogResponse(BaseModel):
    id: int
    email_type: str
    recipient_email: str
    resend_message_id: str | None
    status: str
    error: str | None
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class CampaignResponse(BaseModel):
    id: int
    original_order_id: int
    user_id: int
    asset_id: int
    step: str
    status: str
    next_action_at: datetime
    upsale1_sent_at: datetime | None
    upsale1_order_id: int | None
    upsale2_sent_at: datetime | None
    upsale2_order_id: int | None
    upsale2_reminder_sent_at: datetime | None
    bonus_sent_at: datetime | None
    bonus_order_id: int | None
    upsale3_sent_at: datetime | None
    upsale3_order_id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    expires_at: datetime

    model_config = {"from_attributes": True}


class CampaignDetailResponse(CampaignResponse):
    email_logs: list[CampaignEmailLogResponse] = []
