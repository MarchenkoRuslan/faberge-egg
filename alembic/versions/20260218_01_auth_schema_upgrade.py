"""auth schema upgrade

Revision ID: 20260218_01
Revises:
Create Date: 2026-02-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _ensure_user_columns(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("terms_accepted_ip", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_users_id", "users", ["id"], unique=False)
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        return

    if not _column_exists(inspector, "users", "display_name"):
        op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))
    if not _column_exists(inspector, "users", "is_email_verified"):
        # Legacy users must remain able to log in after upgrade.
        op.add_column(
            "users",
            sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "is_email_verified",
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
    if not _column_exists(inspector, "users", "email_verified_at"):
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(inspector, "users", "terms_accepted_at"):
        op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists(inspector, "users", "terms_accepted_ip"):
        op.add_column("users", sa.Column("terms_accepted_ip", sa.String(length=64), nullable=True))

    op.execute(sa.text("UPDATE users SET is_email_verified = TRUE WHERE is_email_verified IS NULL"))
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "is_email_verified",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )


def _ensure_lot_and_order_tables(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "lots"):
        op.create_table(
            "lots",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("total_fractions", sa.Integer(), nullable=False),
            sa.Column("special_price_fractions_cap", sa.Integer(), nullable=False),
            sa.Column("price_special_eur", sa.Numeric(10, 4), nullable=False),
            sa.Column("price_nominal_eur", sa.Numeric(10, 4), nullable=False),
            sa.Column("sold_special_fractions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_lots_id", "lots", ["id"], unique=False)
        op.create_index("ix_lots_slug", "lots", ["slug"], unique=True)

    if not _table_exists(inspector, "orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
            sa.Column("fraction_count", sa.Integer(), nullable=False),
            sa.Column("amount_eur_cents", sa.Integer(), nullable=False),
            sa.Column("payment_method", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("external_payment_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_orders_id", "orders", ["id"], unique=False)
    elif not _column_exists(inspector, "orders", "external_payment_id"):
        op.add_column("orders", sa.Column("external_payment_id", sa.String(length=255), nullable=True))


def _ensure_token_tables(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "one_time_tokens"):
        op.create_table(
            "one_time_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_one_time_tokens_id", "one_time_tokens", ["id"], unique=False)
        op.create_index("ix_one_time_tokens_user_id", "one_time_tokens", ["user_id"], unique=False)
        op.create_index("ix_one_time_tokens_purpose", "one_time_tokens", ["purpose"], unique=False)
        op.create_index("ix_one_time_tokens_token_hash", "one_time_tokens", ["token_hash"], unique=True)

    if not _table_exists(inspector, "refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_id", sa.Integer(), sa.ForeignKey("refresh_tokens.id"), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"], unique=False)
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
        op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _ensure_user_columns(inspector)
    inspector = sa.inspect(bind)
    _ensure_lot_and_order_tables(inspector)
    inspector = sa.inspect(bind)
    _ensure_token_tables(inspector)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "refresh_tokens"):
        op.drop_table("refresh_tokens")
    if _table_exists(inspector, "one_time_tokens"):
        op.drop_table("one_time_tokens")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "users"):
        if _column_exists(inspector, "users", "terms_accepted_ip"):
            op.drop_column("users", "terms_accepted_ip")
        if _column_exists(inspector, "users", "terms_accepted_at"):
            op.drop_column("users", "terms_accepted_at")
        if _column_exists(inspector, "users", "email_verified_at"):
            op.drop_column("users", "email_verified_at")
        if _column_exists(inspector, "users", "is_email_verified"):
            op.drop_column("users", "is_email_verified")
        if _column_exists(inspector, "users", "display_name"):
            op.drop_column("users", "display_name")
