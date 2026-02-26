"""add blockchain_wallets and fraction_transfers tables

Revision ID: 20260226_01
Revises: 20260225_03
Create Date: 2026-02-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260226_01"
down_revision: Union[str, None] = "20260225_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blockchain_wallets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("address", sa.String(255), unique=True, nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blockchain_wallets_address", "blockchain_wallets", ["address"])

    op.create_table(
        "fraction_transfers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fraction_count", sa.Integer(), nullable=False),
        sa.Column("transfer_type", sa.String(50), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("blockchain_tx_hash", sa.String(255), nullable=True),
        sa.Column("blockchain_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fraction_transfers_asset_id", "fraction_transfers", ["asset_id"])
    op.create_index("ix_fraction_transfers_order_id", "fraction_transfers", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_fraction_transfers_order_id", table_name="fraction_transfers")
    op.drop_index("ix_fraction_transfers_asset_id", table_name="fraction_transfers")
    op.drop_table("fraction_transfers")
    op.drop_index("ix_blockchain_wallets_address", table_name="blockchain_wallets")
    op.drop_table("blockchain_wallets")
