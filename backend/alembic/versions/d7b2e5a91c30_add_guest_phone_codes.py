"""add guest_phone_codes

Revision ID: d7b2e5a91c30
Revises: a1f3c8d27e64
Create Date: 2026-09-25

I codici WhatsApp di chi prenota dal portale senza account: una riga per
numero. Tabella nuova e vuota, niente da migrare.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7b2e5a91c30"
down_revision: Union[str, None] = "a1f3c8d27e64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guest_phone_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sends_in_window", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guest_phone_codes_phone", "guest_phone_codes", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_guest_phone_codes_phone", table_name="guest_phone_codes")
    op.drop_table("guest_phone_codes")
