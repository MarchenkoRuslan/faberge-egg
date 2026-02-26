"""add indexes on orders.user_id, orders.asset_id, fraction_transfers.asset_id

Revision ID: 20260226_04
Revises: 20260226_03
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260226_04"
down_revision: Union[str, None] = "20260226_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)
    op.create_index("ix_orders_asset_id", "orders", ["asset_id"], unique=False)
    op.create_index("ix_fraction_transfers_asset_id", "fraction_transfers", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_fraction_transfers_asset_id", table_name="fraction_transfers")
    op.drop_index("ix_orders_asset_id", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
