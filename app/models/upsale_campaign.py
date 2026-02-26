from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class UpsaleCampaign(Base):
    __tablename__ = "upsale_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    original_order_id = Column(
        Integer, ForeignKey("orders.id"), nullable=False, index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)

    step = Column(String(50), nullable=False, default="upsale1_pending")
    status = Column(String(20), nullable=False, default="active", index=True)

    next_action_at = Column(DateTime(timezone=True), nullable=False, index=True)

    upsale1_sent_at = Column(DateTime(timezone=True), nullable=True)
    upsale1_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    upsale2_sent_at = Column(DateTime(timezone=True), nullable=True)
    upsale2_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    upsale2_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    bonus_sent_at = Column(DateTime(timezone=True), nullable=True)
    bonus_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    upsale3_sent_at = Column(DateTime(timezone=True), nullable=True)
    upsale3_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)

    original_order = relationship(
        "Order", foreign_keys=[original_order_id], lazy="joined",
    )
    user = relationship("User", lazy="joined")
    email_logs = relationship(
        "CampaignEmailLog", back_populates="campaign",
        order_by="CampaignEmailLog.sent_at",
    )


class CampaignEmailLog(Base):
    __tablename__ = "campaign_email_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(
        Integer, ForeignKey("upsale_campaigns.id"), nullable=False, index=True,
    )
    email_type = Column(String(50), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    resend_message_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("UpsaleCampaign", back_populates="email_logs")
