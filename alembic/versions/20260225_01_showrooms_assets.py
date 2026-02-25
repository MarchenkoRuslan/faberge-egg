"""showrooms, assets and media tables

Revision ID: 20260225_01
Revises: 20260218_01
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260225_01"
down_revision: Union[str, None] = "20260218_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "showrooms"):
        op.create_table(
            "showrooms",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("headline", sa.String(length=500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column(
                "status", sa.String(length=50), nullable=False, server_default="active"
            ),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_showrooms_id", "showrooms", ["id"], unique=False)
        op.create_index("ix_showrooms_slug", "showrooms", ["slug"], unique=True)

    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "assets"):
        op.create_table(
            "assets",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "showroom_id", sa.Integer(), sa.ForeignKey("showrooms.id"), nullable=False
            ),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("headline", sa.String(length=500), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column(
                "status", sa.String(length=50), nullable=False, server_default="active"
            ),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_assets_id", "assets", ["id"], unique=False)
        op.create_index("ix_assets_slug", "assets", ["slug"], unique=True)
        op.create_index("ix_assets_showroom_id", "assets", ["showroom_id"], unique=False)

    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "asset_media"):
        op.create_table(
            "asset_media",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False
            ),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("media_type", sa.String(length=50), nullable=False),
            sa.Column("storage_key", sa.String(length=1024), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("alt_text", sa.String(length=500), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_asset_media_id", "asset_media", ["id"], unique=False)
        op.create_index("ix_asset_media_asset_id", "asset_media", ["asset_id"], unique=False)

    inspector = sa.inspect(bind)

    if _table_exists(inspector, "lots") and not _column_exists(inspector, "lots", "asset_id"):
        op.add_column(
            "lots",
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "lots") and _column_exists(inspector, "lots", "asset_id"):
        op.drop_column("lots", "asset_id")

    if _table_exists(inspector, "asset_media"):
        op.drop_table("asset_media")
    if _table_exists(inspector, "assets"):
        op.drop_table("assets")
    if _table_exists(inspector, "showrooms"):
        op.drop_table("showrooms")
