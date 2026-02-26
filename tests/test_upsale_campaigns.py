"""Tests for upsale campaign state machine, processor, and integration."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")

from app.models.order import Order  # noqa: E402
from app.models.upsale_campaign import CampaignEmailLog, UpsaleCampaign  # noqa: E402
from app.services.upsale_campaign_service import (  # noqa: E402
    create_campaign,
    on_upsale_purchase,
    process_due_campaigns,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_order(db: Session, user_id: int, asset_id: int, status: str = "paid") -> Order:
    order = Order(
        user_id=user_id,
        asset_id=asset_id,
        fraction_count=100,
        amount_eur_cents=300,
        payment_method="stripe",
        status=status,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------


@patch("app.services.upsale_campaign_service.settings")
def test_create_campaign_disabled(mock_settings, db, test_user, test_asset):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = False
    order = _make_order(db, test_user.id, test_asset.id)
    result = create_campaign(db, order)
    assert result is None


@patch("app.services.upsale_campaign_service.settings")
def test_create_campaign_success(mock_settings, db, test_user, test_asset):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = create_campaign(db, order)
    db.commit()

    assert campaign is not None
    assert campaign.step == "upsale1_pending"
    assert campaign.status == "active"
    assert campaign.user_id == test_user.id
    assert campaign.asset_id == test_asset.id
    assert campaign.original_order_id == order.id
    expires = campaign.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert expires > _utcnow()


@patch("app.services.upsale_campaign_service.settings")
def test_create_campaign_idempotent(mock_settings, db, test_user, test_asset):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"
    order = _make_order(db, test_user.id, test_asset.id)
    c1 = create_campaign(db, order)
    db.commit()
    assert c1 is not None

    order2 = _make_order(db, test_user.id, test_asset.id)
    c2 = create_campaign(db, order2)
    assert c2 is None

    count = db.query(UpsaleCampaign).count()
    assert count == 1


# ---------------------------------------------------------------------------
# on_upsale_purchase
# ---------------------------------------------------------------------------


@patch("app.services.upsale_campaign_service.settings")
def test_on_upsale_purchase_advances_upsale1_sent(mock_settings, db, test_user, test_asset):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = create_campaign(db, order)
    db.commit()

    campaign.step = "upsale1_sent"
    campaign.upsale1_sent_at = _utcnow()
    db.commit()

    upsale_order = _make_order(db, test_user.id, test_asset.id)
    advanced = on_upsale_purchase(db, upsale_order)
    db.commit()

    assert advanced is True
    db.refresh(campaign)
    assert campaign.step == "upsale2_pending"
    assert campaign.upsale1_order_id == upsale_order.id


@patch("app.services.upsale_campaign_service.settings")
def test_on_upsale_purchase_advances_bonus_sent(mock_settings, db, test_user, test_asset):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = create_campaign(db, order)
    db.commit()

    campaign.step = "bonus_sent"
    campaign.bonus_sent_at = _utcnow()
    db.commit()

    upsale_order = _make_order(db, test_user.id, test_asset.id)
    advanced = on_upsale_purchase(db, upsale_order)
    db.commit()

    assert advanced is True
    db.refresh(campaign)
    assert campaign.step == "upsale3_pending"
    assert campaign.bonus_order_id == upsale_order.id


def test_on_upsale_purchase_no_campaign(db, test_user, test_asset):
    order = _make_order(db, test_user.id, test_asset.id)
    assert on_upsale_purchase(db, order) is False


# ---------------------------------------------------------------------------
# process_due_campaigns -- step transitions
# ---------------------------------------------------------------------------


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-id-123")
def test_process_upsale1_pending_sends_email(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = create_campaign(db, order)
    db.commit()

    campaign.next_action_at = _utcnow() - timedelta(minutes=1)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "upsale1_sent"
    assert campaign.upsale1_sent_at is not None
    mock_send.assert_called_once()

    logs = db.query(CampaignEmailLog).filter(CampaignEmailLog.campaign_id == campaign.id).all()
    assert len(logs) == 1
    assert logs[0].email_type == "upsale1"
    assert logs[0].status == "sent"
    assert logs[0].resend_message_id == "msg-id-123"


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-id-456")
def test_process_upsale1_sent_no_purchase_goes_to_bonus(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"

    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale1_sent",
        status="active",
        upsale1_sent_at=_utcnow() - timedelta(days=8),
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "bonus_pending"


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-id-789")
def test_process_upsale1_sent_with_purchase_goes_to_upsale2(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"

    original_order = _make_order(db, test_user.id, test_asset.id)
    sent_time = _utcnow() - timedelta(days=3)
    campaign = UpsaleCampaign(
        original_order_id=original_order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale1_sent",
        status="active",
        upsale1_sent_at=sent_time,
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    _make_order(db, test_user.id, test_asset.id)

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "upsale2_pending"
    assert campaign.upsale1_order_id is not None


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-bonus")
def test_process_bonus_pending_sends_email(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"

    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="bonus_pending",
        status="active",
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "bonus_sent"
    assert campaign.bonus_sent_at is not None
    mock_send.assert_called_once()


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-u3")
def test_process_bonus_sent_no_purchase_completes(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"

    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="bonus_sent",
        status="active",
        bonus_sent_at=_utcnow() - timedelta(days=8),
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "completed"
    assert campaign.status == "completed"


@patch("app.services.upsale_campaign_service.settings")
@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-u3")
def test_process_upsale3_pending_completes(
    mock_send, mock_settings, db, test_user, test_asset,
):
    mock_settings.UPSALE_CAMPAIGN_ENABLED = True
    mock_settings.UPSALE_CAMPAIGN_EXPIRE_DAYS = 60
    mock_settings.FRONTEND_URL = "http://localhost:3000"

    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale3_pending",
        status="active",
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.step == "completed"
    assert campaign.status == "completed"
    assert campaign.upsale3_sent_at is not None
    mock_send.assert_called_once()


# ---------------------------------------------------------------------------
# Expiration
# ---------------------------------------------------------------------------


def test_process_expired_campaign(db, test_user, test_asset):
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale2_pending",
        status="active",
        next_action_at=_utcnow() - timedelta(minutes=1),
        expires_at=_utcnow() - timedelta(days=1),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 1

    db.refresh(campaign)
    assert campaign.status == "expired"
    assert campaign.step == "completed"


# ---------------------------------------------------------------------------
# Not due yet -- should not be processed
# ---------------------------------------------------------------------------


@patch("app.services.upsale_campaign_service.send_upsale_email", return_value="msg-id")
def test_process_skips_future_campaigns(mock_send, db, test_user, test_asset):
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale1_pending",
        status="active",
        next_action_at=_utcnow() + timedelta(days=3),
        expires_at=_utcnow() + timedelta(days=50),
    )
    db.add(campaign)
    db.commit()

    processed = process_due_campaigns(db)
    assert processed == 0
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


def test_list_campaigns_unauthenticated(client):
    resp = client.get("/api/admin/campaigns")
    assert resp.status_code == 401


def test_list_campaigns_empty(client, auth_headers):
    resp = client.get("/api/admin/campaigns", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_and_get_campaign(client, auth_headers, db, test_user, test_asset):
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale1_pending",
        status="active",
        next_action_at=_utcnow() + timedelta(days=4),
        expires_at=_utcnow() + timedelta(days=60),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    resp = client.get("/api/admin/campaigns", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == campaign.id

    resp = client.get(f"/api/admin/campaigns/{campaign.id}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["step"] == "upsale1_pending"
    assert "email_logs" in detail


def test_cancel_campaign(client, auth_headers, db, test_user, test_asset):
    order = _make_order(db, test_user.id, test_asset.id)
    campaign = UpsaleCampaign(
        original_order_id=order.id,
        user_id=test_user.id,
        asset_id=test_asset.id,
        step="upsale1_sent",
        status="active",
        next_action_at=_utcnow() + timedelta(days=4),
        expires_at=_utcnow() + timedelta(days=60),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    resp = client.post(f"/api/admin/campaigns/{campaign.id}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = client.post(f"/api/admin/campaigns/{campaign.id}/cancel", headers=auth_headers)
    assert resp.status_code == 409


def test_get_campaign_not_found(client, auth_headers):
    resp = client.get("/api/admin/campaigns/99999", headers=auth_headers)
    assert resp.status_code == 404
