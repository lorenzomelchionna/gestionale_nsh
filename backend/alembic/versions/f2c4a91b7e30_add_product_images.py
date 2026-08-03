"""add product_images

Revision ID: f2c4a91b7e30
Revises: d7a1c93f2b48
Create Date: 2026-08-03

The photo lives in its own table rather than as a column on `products`, so the
inventory listing never drags the bytes along. `products.photo_url` already
existed and is reused: it now holds the public URL built from the token.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2c4a91b7e30"
down_revision: Union[str, None] = "d7a1c93f2b48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One photo per product: the upload endpoint replaces rather than appends.
        sa.UniqueConstraint("product_id"),
    )
    # The token is the only way in from the public endpoint, so it is both the
    # lookup key and unique.
    op.create_index(
        op.f("ix_product_images_token"), "product_images", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_images_token"), table_name="product_images")
    op.drop_table("product_images")
