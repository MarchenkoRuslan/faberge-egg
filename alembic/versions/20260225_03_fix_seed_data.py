"""fix seed data: showroom meta and missing asset media

Revision ID: 20260225_03
Revises: 20260225_02
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260225_03"
down_revision: Union[str, None] = "20260225_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = inspector.get_table_names()
    if "showrooms" not in table_names or "assets" not in table_names or "asset_media" not in table_names:
        return

    # 1. Set showroom meta with image storage keys (only when meta is NULL)
    bind.execute(
        sa.text(
            """
            UPDATE showrooms
            SET meta = :meta ::jsonb
            WHERE slug = 'latvian-treasure' AND meta IS NULL
            """
        ),
        {"meta": '{"image_key": "latvian-treasure/showroom-image.jpg", "background_image_key": "latvian-treasure/showroom-background.jpg"}'},
    )

    # 2. Insert missing asset_media records for faberge-egg asset
    #    Idempotent: skip if storage_key already exists
    missing_media = [
        {
            "kind": "gallery",
            "media_type": "image/jpeg",
            "storage_key": "latvian-treasure/faberge-egg/gallery-3.jpg",
            "filename": "gallery-3.jpg",
            "alt_text": "Faberge Egg side view",
            "sort_order": 3,
        },
        {
            "kind": "gallery",
            "media_type": "image/jpeg",
            "storage_key": "latvian-treasure/faberge-egg/gallery-4.jpg",
            "filename": "gallery-4.jpg",
            "alt_text": "Faberge Egg alternate angle",
            "sort_order": 4,
        },
    ]

    for media in missing_media:
        bind.execute(
            sa.text(
                """
                INSERT INTO asset_media (asset_id, kind, media_type, storage_key, filename, alt_text, sort_order)
                SELECT a.id,
                       :kind ::varchar,
                       :media_type ::varchar,
                       :storage_key ::varchar,
                       :filename ::varchar,
                       :alt_text ::varchar,
                       :sort_order
                FROM assets a
                WHERE a.slug = 'faberge-egg'
                  AND NOT EXISTS (
                      SELECT 1 FROM asset_media am
                      WHERE am.asset_id = a.id AND am.storage_key = :storage_key ::varchar
                  )
                """
            ),
            media,
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Remove the two gallery images added by this migration
    for key in [
        "latvian-treasure/faberge-egg/gallery-3.jpg",
        "latvian-treasure/faberge-egg/gallery-4.jpg",
    ]:
        bind.execute(
            sa.text("DELETE FROM asset_media WHERE storage_key = :key"),
            {"key": key},
        )

    # Reset showroom meta to NULL
    bind.execute(
        sa.text(
            """
            UPDATE showrooms SET meta = NULL
            WHERE slug = 'latvian-treasure'
            """
        )
    )
