"""Upsale campaign state machine and periodic processor.

Sends a series of upsale emails after a user purchases fractions of an asset.
The funnel branches based on whether the user made additional purchases.

Lifecycle (delays in ``_STEP_DELAYS``):

  Purchase ─(+4d)─> upsale1_pending ─[send]─> upsale1_sent ─(+7d check)─>
    ├─ purchased ─(+14d)─> upsale2_pending ─[send]─> upsale2_sent ─(+14d)─>
    │     ├─ purchased ─(+30d)─> upsale3_pending ─[send]─> completed
    │     └─ not bought ─> upsale2_reminder_pending ─[send]─> upsale2_reminder_sent ─> completed
    └─ not bought ─> bonus_pending ─[send]─> bonus_sent ─(+7d)─>
          ├─ purchased ─(+30d)─> upsale3_pending ─[send]─> completed
          └─ no response ─> completed

Integration points:
  - ``settle_order_payment()`` calls ``create_campaign()`` / ``on_upsale_purchase()``
  - Background asyncio task in ``app/main.py`` lifespan calls ``process_due_campaigns()``
  - Admin API at ``/api/admin/campaigns`` for monitoring

Configuration (env vars via ``app/config.py``):
  - ``UPSALE_CAMPAIGN_ENABLED`` (default False) -- master switch
  - ``UPSALE_CAMPAIGN_PROCESS_INTERVAL_SECONDS`` (default 300)
  - ``UPSALE_CAMPAIGN_EXPIRE_DAYS`` (default 60)
  - ``RESEND_TEMPLATE_UPSALE1``, ``_UPSALE2``, ``_UPSALE3``, ``_BONUS_UPSALE``
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.order import Order
from app.models.upsale_campaign import CampaignEmailLog, UpsaleCampaign
from app.models.user import User
from app.services.email_service import send_upsale_email

logger = logging.getLogger(__name__)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce naive datetimes (e.g. from SQLite) to UTC-aware."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# Delay from campaign creation / previous step completion to the next action.
# For *_pending steps:  how long to wait before sending the email.
# For *_sent steps:     how long to wait before checking if the user purchased.
_STEP_DELAYS = {
    "upsale1_pending": timedelta(days=4),       # wait 4 days after purchase
    "upsale1_sent": timedelta(days=7),           # check for response after 7 days
    "upsale2_pending": timedelta(days=14),       # send upsale2 14 days after upsale1 purchase
    "upsale2_sent": timedelta(days=14),          # check for response after 14 days
    "upsale2_reminder_pending": timedelta(days=0),  # send reminder immediately
    "upsale2_reminder_sent": timedelta(days=7),  # final check after 7 days
    "bonus_pending": timedelta(days=0),          # send bonus immediately (user didn't buy upsale1)
    "bonus_sent": timedelta(days=7),             # check for response after 7 days
    "upsale3_pending": timedelta(days=30),       # send upsale3 30 days after previous purchase
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_buy_link(asset_id: int) -> str:
    frontend = settings.FRONTEND_URL.rstrip("/")
    return f"{frontend}/assets/{asset_id}"


def _has_upsale_purchase(
    db: Session,
    *,
    user_id: int,
    asset_id: int,
    since: datetime,
    exclude_order_id: int | None = None,
) -> Order | None:
    """Check whether the user purchased additional fractions of the asset since *since*."""
    q = db.query(Order).filter(
        Order.user_id == user_id,
        Order.asset_id == asset_id,
        Order.status == "paid",
        Order.created_at > since,
    )
    if exclude_order_id is not None:
        q = q.filter(Order.id != exclude_order_id)
    return q.order_by(Order.created_at.desc()).first()


def _record_email_log(
    db: Session,
    *,
    campaign: UpsaleCampaign,
    email_type: str,
    recipient_email: str,
    resend_message_id: str | None,
    status: str,
    error: str | None = None,
) -> None:
    log = CampaignEmailLog(
        campaign_id=campaign.id,
        email_type=email_type,
        recipient_email=recipient_email,
        resend_message_id=resend_message_id,
        status=status,
        error=error,
    )
    db.add(log)


def _send_campaign_email(
    db: Session,
    *,
    campaign: UpsaleCampaign,
    email_type: str,
) -> bool:
    """Send an email for the campaign, log the result. Returns True on success."""
    user = db.query(User).filter(User.id == campaign.user_id).first()
    if not user:
        logger.error("Campaign %d: user %d not found", campaign.id, campaign.user_id)
        return False

    from app.models.asset import Asset
    asset = db.query(Asset).filter(Asset.id == campaign.asset_id).first()
    asset_name = asset.name if asset else "asset"
    buy_link = _build_buy_link(campaign.asset_id)

    try:
        msg_id = send_upsale_email(
            to_email=user.email,
            display_name=user.display_name,
            email_type=email_type,
            asset_name=asset_name,
            buy_link=buy_link,
        )
    except RuntimeError as exc:
        logger.warning(
            "Campaign %d: skipping email %s — %s", campaign.id, email_type, exc,
        )
        _record_email_log(
            db,
            campaign=campaign,
            email_type=email_type,
            recipient_email=user.email,
            resend_message_id=None,
            status="failed",
            error=str(exc),
        )
        return False

    _record_email_log(
        db,
        campaign=campaign,
        email_type=email_type,
        recipient_email=user.email,
        resend_message_id=msg_id,
        status="sent" if msg_id else "failed",
        error=None if msg_id else "send returned None",
    )
    return bool(msg_id)


def _advance(campaign: UpsaleCampaign, step: str, delay: timedelta) -> None:
    campaign.step = step
    campaign.next_action_at = _now() + delay


def _complete(campaign: UpsaleCampaign) -> None:
    campaign.step = "completed"
    campaign.status = "completed"
    campaign.next_action_at = _now()


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def _handle_upsale1_pending(db: Session, c: UpsaleCampaign) -> None:
    if not _send_campaign_email(db, campaign=c, email_type="upsale1"):
        c.next_action_at = _now() + timedelta(minutes=5)
        return
    c.upsale1_sent_at = _now()
    _advance(c, "upsale1_sent", _STEP_DELAYS["upsale1_sent"])


def _handle_upsale1_sent(db: Session, c: UpsaleCampaign) -> None:
    since = c.upsale1_sent_at or c.created_at
    upsale_order = _has_upsale_purchase(
        db, user_id=c.user_id, asset_id=c.asset_id, since=since,
        exclude_order_id=c.original_order_id,
    )
    if upsale_order:
        c.upsale1_order_id = upsale_order.id
        _advance(c, "upsale2_pending", _STEP_DELAYS["upsale2_pending"])
    else:
        _advance(c, "bonus_pending", _STEP_DELAYS["bonus_pending"])


def _handle_upsale2_pending(db: Session, c: UpsaleCampaign) -> None:
    if not _send_campaign_email(db, campaign=c, email_type="upsale2"):
        c.next_action_at = _now() + timedelta(minutes=5)
        return
    c.upsale2_sent_at = _now()
    _advance(c, "upsale2_sent", _STEP_DELAYS["upsale2_sent"])


def _handle_upsale2_sent(db: Session, c: UpsaleCampaign) -> None:
    since = c.upsale2_sent_at or c.created_at
    upsale_order = _has_upsale_purchase(
        db, user_id=c.user_id, asset_id=c.asset_id, since=since,
        exclude_order_id=c.original_order_id,
    )
    if upsale_order:
        c.upsale2_order_id = upsale_order.id
        _advance(c, "upsale3_pending", _STEP_DELAYS["upsale3_pending"])
    else:
        _advance(c, "upsale2_reminder_pending", _STEP_DELAYS["upsale2_reminder_pending"])


def _handle_upsale2_reminder_pending(db: Session, c: UpsaleCampaign) -> None:
    if not _send_campaign_email(db, campaign=c, email_type="upsale2_reminder"):
        c.next_action_at = _now() + timedelta(minutes=5)
        return
    c.upsale2_reminder_sent_at = _now()
    _advance(c, "upsale2_reminder_sent", _STEP_DELAYS["upsale2_reminder_sent"])


def _handle_upsale2_reminder_sent(db: Session, c: UpsaleCampaign) -> None:
    since = c.upsale2_reminder_sent_at or c.created_at
    upsale_order = _has_upsale_purchase(
        db, user_id=c.user_id, asset_id=c.asset_id, since=since,
        exclude_order_id=c.original_order_id,
    )
    if upsale_order:
        c.upsale2_order_id = upsale_order.id
    _complete(c)


def _handle_bonus_pending(db: Session, c: UpsaleCampaign) -> None:
    if not _send_campaign_email(db, campaign=c, email_type="bonus"):
        c.next_action_at = _now() + timedelta(minutes=5)
        return
    c.bonus_sent_at = _now()
    _advance(c, "bonus_sent", _STEP_DELAYS["bonus_sent"])


def _handle_bonus_sent(db: Session, c: UpsaleCampaign) -> None:
    since = c.bonus_sent_at or c.created_at
    upsale_order = _has_upsale_purchase(
        db, user_id=c.user_id, asset_id=c.asset_id, since=since,
        exclude_order_id=c.original_order_id,
    )
    if upsale_order:
        c.bonus_order_id = upsale_order.id
        _advance(c, "upsale3_pending", _STEP_DELAYS["upsale3_pending"])
    else:
        _complete(c)


def _handle_upsale3_pending(db: Session, c: UpsaleCampaign) -> None:
    if not _send_campaign_email(db, campaign=c, email_type="upsale3"):
        c.next_action_at = _now() + timedelta(minutes=5)
        return
    c.upsale3_sent_at = _now()
    _complete(c)


_STEP_HANDLERS = {
    "upsale1_pending": _handle_upsale1_pending,
    "upsale1_sent": _handle_upsale1_sent,
    "upsale2_pending": _handle_upsale2_pending,
    "upsale2_sent": _handle_upsale2_sent,
    "upsale2_reminder_pending": _handle_upsale2_reminder_pending,
    "upsale2_reminder_sent": _handle_upsale2_reminder_sent,
    "bonus_pending": _handle_bonus_pending,
    "bonus_sent": _handle_bonus_sent,
    "upsale3_pending": _handle_upsale3_pending,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_campaign(db: Session, order: Order) -> UpsaleCampaign | None:
    """Create a new upsale campaign for a paid order.

    Returns None if campaigns are disabled or a campaign already exists
    for this (user, asset) pair.
    """
    if not settings.UPSALE_CAMPAIGN_ENABLED:
        return None

    existing = (
        db.query(UpsaleCampaign)
        .filter(
            UpsaleCampaign.user_id == order.user_id,
            UpsaleCampaign.asset_id == order.asset_id,
            UpsaleCampaign.status == "active",
        )
        .first()
    )
    if existing:
        logger.debug(
            "Active campaign %d already exists for user=%d asset=%d; skipping creation",
            existing.id, order.user_id, order.asset_id,
        )
        return None

    now = _now()
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=order.user_id,
        asset_id=order.asset_id,
        step="upsale1_pending",
        status="active",
        next_action_at=now + _STEP_DELAYS["upsale1_pending"],
        expires_at=now + timedelta(days=settings.UPSALE_CAMPAIGN_EXPIRE_DAYS),
    )
    db.add(campaign)
    db.flush()
    logger.info(
        "Created upsale campaign %d for order=%d user=%d asset=%d",
        campaign.id, order.id, order.user_id, order.asset_id,
    )
    return campaign


def on_upsale_purchase(db: Session, order: Order) -> bool:
    """Called when a paid order is detected for a user+asset with an active campaign.

    Immediately advances the campaign past the current *_sent check step
    so the user doesn't have to wait for the periodic processor.

    Returns True if a campaign was advanced.
    """
    campaign = (
        db.query(UpsaleCampaign)
        .filter(
            UpsaleCampaign.user_id == order.user_id,
            UpsaleCampaign.asset_id == order.asset_id,
            UpsaleCampaign.status == "active",
        )
        .first()
    )
    if not campaign:
        return False

    step = campaign.step
    advanced = False

    if step == "upsale1_sent":
        campaign.upsale1_order_id = order.id
        _advance(campaign, "upsale2_pending", _STEP_DELAYS["upsale2_pending"])
        advanced = True
    elif step == "upsale2_sent":
        campaign.upsale2_order_id = order.id
        _advance(campaign, "upsale3_pending", _STEP_DELAYS["upsale3_pending"])
        advanced = True
    elif step == "upsale2_reminder_sent":
        campaign.upsale2_order_id = order.id
        _complete(campaign)
        advanced = True
    elif step == "bonus_sent":
        campaign.bonus_order_id = order.id
        _advance(campaign, "upsale3_pending", _STEP_DELAYS["upsale3_pending"])
        advanced = True

    if advanced:
        logger.info(
            "Campaign %d advanced from %s via upsale order %d",
            campaign.id, step, order.id,
        )
    return advanced


def process_due_campaigns(db: Session) -> int:
    """Process all campaigns whose next_action_at has passed.

    Returns the number of campaigns processed.
    """
    now = _now()
    campaigns = (
        db.query(UpsaleCampaign)
        .filter(
            UpsaleCampaign.status == "active",
            UpsaleCampaign.next_action_at <= now,
        )
        .all()
    )

    processed = 0
    for campaign in campaigns:
        try:
            if _ensure_aware(campaign.expires_at) <= now:
                campaign.status = "expired"
                campaign.step = "completed"
                logger.info("Campaign %d expired", campaign.id)
                db.commit()
                processed += 1
                continue

            handler = _STEP_HANDLERS.get(campaign.step)
            if not handler:
                logger.warning(
                    "Campaign %d has unknown step %r; marking completed",
                    campaign.id, campaign.step,
                )
                _complete(campaign)
                db.commit()
                processed += 1
                continue

            handler(db, campaign)
            db.commit()
            processed += 1
        except Exception:
            db.rollback()
            logger.exception("Error processing campaign %d step %s", campaign.id, campaign.step)

    if processed:
        logger.info("Processed %d campaign(s)", processed)
    return processed
