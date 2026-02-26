"""add upsale_campaigns and campaign_email_logs tables

Revision ID: 20260226_02
Revises: 20260226_01
Create Date: 2026-02-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260226_02"
down_revision: Union[str, None] = "20260226_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upsale_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("original_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("step", sa.String(50), nullable=False, server_default="upsale1_pending"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("upsale1_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upsale1_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("upsale2_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upsale2_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("upsale2_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bonus_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bonus_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("upsale3_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upsale3_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "campaign_email_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("upsale_campaigns.id"), nullable=False, index=True),
        sa.Column("email_type", sa.String(50), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("resend_message_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("campaign_email_logs")
    op.drop_table("upsale_campaigns")
