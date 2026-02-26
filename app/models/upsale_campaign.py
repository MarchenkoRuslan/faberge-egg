"""Post-purchase upsale email campaign models.

UpsaleCampaign tracks a single user's journey through the upsale funnel
after purchasing fractions of an asset.  CampaignEmailLog is an append-only
audit trail of every email sent (or failed) within a campaign.

State machine steps (see ``app.domains.campaigns.service``):

    upsale1_pending  -> upsale1_sent  -> upsale2_pending | bonus_pending
    upsale2_pending  -> upsale2_sent  -> upsale3_pending | upsale2_reminder_pending
    upsale2_reminder_pending -> upsale2_reminder_sent -> completed
    bonus_pending    -> bonus_sent    -> upsale3_pending | completed
    upsale3_pending  -> upsale3_sent  -> completed

Campaign statuses: active, completed, expired, cancelled.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class UpsaleCampaign(Base):
    """One campaign per (user, asset) after a purchase.

    Fields:
        original_order_id: The order that triggered this campaign.
        step: Current position in the state machine (see module docstring).
        status: ``active`` while running; terminal values are
            ``completed``, ``expired``, ``cancelled``.
        next_action_at: When the background processor should next act on this
            campaign (send email or check for a purchase response).
        *_sent_at: Timestamps of when each email type was dispatched.
        *_order_id: Links to follow-up orders placed by the user in response
            to each upsale email (NULL if no purchase detected).
        expires_at: Hard deadline after which the campaign is marked expired
            regardless of its current step.
    """

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
    """Append-only log of every email dispatched within a campaign.

    Fields:
        email_type: One of ``upsale1``, ``upsale2``, ``upsale2_reminder``,
            ``upsale3``, ``bonus``.
        status: ``sent`` on success, ``failed`` on error.
        resend_message_id: Resend API message ID (for delivery tracking).
        error: Error description when status is ``failed``.
    """

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
