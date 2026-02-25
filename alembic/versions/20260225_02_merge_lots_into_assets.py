"""merge lots table into assets

Revision ID: 20260225_02
Revises: 20260225_01
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260225_02"
down_revision: Union[str, None] = "20260225_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "assets"):
        return

    # 1. Add commerce columns to assets
    if not _column_exists(inspector, "assets", "total_fractions"):
        op.add_column("assets", sa.Column("total_fractions", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if not _column_exists(inspector, "assets", "special_price_fractions_cap"):
        op.add_column("assets", sa.Column("special_price_fractions_cap", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if not _column_exists(inspector, "assets", "price_special_eur"):
        op.add_column("assets", sa.Column("price_special_eur", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")))
    if not _column_exists(inspector, "assets", "price_nominal_eur"):
        op.add_column("assets", sa.Column("price_nominal_eur", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")))
    if not _column_exists(inspector, "assets", "sold_special_fractions"):
        op.add_column("assets", sa.Column("sold_special_fractions", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if not _column_exists(inspector, "assets", "is_active"):
        op.add_column("assets", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    # 2. Migrate data from lots to assets (where linked)
    if _table_exists(inspector, "lots"):
        inspector = sa.inspect(bind)
        if _column_exists(inspector, "lots", "asset_id"):
            op.execute(
                """
                UPDATE assets SET
                    total_fractions = lots.total_fractions,
                    special_price_fractions_cap = lots.special_price_fractions_cap,
                    price_special_eur = lots.price_special_eur,
                    price_nominal_eur = lots.price_nominal_eur,
                    sold_special_fractions = lots.sold_special_fractions,
                    is_active = lots.is_active
                FROM lots
                WHERE assets.id = lots.asset_id
                """
            )

    # 3. Add asset_id column to orders
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "orders") and not _column_exists(inspector, "orders", "asset_id"):
        op.add_column(
            "orders",
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=True),
        )

    # 4. Populate orders.asset_id from lots
    inspector = sa.inspect(bind)
    if (
        _table_exists(inspector, "lots")
        and _table_exists(inspector, "orders")
        and _column_exists(inspector, "orders", "lot_id")
        and _column_exists(inspector, "orders", "asset_id")
        and _column_exists(inspector, "lots", "asset_id")
    ):
        op.execute(
            """
            UPDATE orders SET asset_id = lots.asset_id
            FROM lots
            WHERE orders.lot_id = lots.id
            """
        )

    # 5. Drop lot_id from orders
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "orders") and _column_exists(inspector, "orders", "lot_id"):
        op.drop_column("orders", "lot_id")

    # 6. Drop asset_id from lots (remove FK before dropping table)
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "lots") and _column_exists(inspector, "lots", "asset_id"):
        op.drop_column("lots", "asset_id")

    # 7. Drop lots table
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "lots"):
        op.drop_table("lots")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Recreate lots table
    if not _table_exists(inspector, "lots"):
        op.create_table(
            "lots",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("total_fractions", sa.Integer(), nullable=False),
            sa.Column("special_price_fractions_cap", sa.Integer(), nullable=False),
            sa.Column("price_special_eur", sa.Numeric(10, 4), nullable=False),
            sa.Column("price_nominal_eur", sa.Numeric(10, 4), nullable=False),
            sa.Column("sold_special_fractions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_lots_id", "lots", ["id"], unique=False)
        op.create_index("ix_lots_slug", "lots", ["slug"], unique=True)

    # Restore lot_id on orders
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "orders") and not _column_exists(inspector, "orders", "lot_id"):
        op.add_column(
            "orders",
            sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=True),
        )

    # Drop asset_id from orders
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "orders") and _column_exists(inspector, "orders", "asset_id"):
        op.drop_column("orders", "asset_id")

    # Drop commerce columns from assets
    for col_name in [
        "is_active", "sold_special_fractions", "price_nominal_eur",
        "price_special_eur", "special_price_fractions_cap", "total_fractions",
    ]:
        inspector = sa.inspect(bind)
        if _table_exists(inspector, "assets") and _column_exists(inspector, "assets", col_name):
            op.drop_column("assets", col_name)
