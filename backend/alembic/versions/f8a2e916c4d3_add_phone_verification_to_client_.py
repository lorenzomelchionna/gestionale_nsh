"""add phone verification to client_accounts

Revision ID: f8a2e916c4d3
Revises: b6e21c8f0a53
Create Date: 2026-09-22

Stesso schema di d7a1c93f2b48 (email), un canale dopo: gli account che esistono
già hanno un numero mai controllato, quindi restano com'erano invece di essere
bloccati fuori da un portale che già usano. I nuovi partono a false e lo
guadagnano col codice mandato su WhatsApp.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a2e916c4d3"
down_revision: Union[str, None] = "b6e21c8f0a53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_accounts",
        sa.Column(
            "phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "client_accounts",
        sa.Column("phone_verification_code_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "client_accounts",
        sa.Column("phone_verification_expires", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_accounts",
        sa.Column(
            "phone_verification_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # Grandfather chi si è registrato prima che questo esistesse.
    op.execute("UPDATE client_accounts SET phone_verified = true")

    op.alter_column("client_accounts", "phone_verified", server_default=None)
    op.alter_column("client_accounts", "phone_verification_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("client_accounts", "phone_verification_attempts")
    op.drop_column("client_accounts", "phone_verification_expires")
    op.drop_column("client_accounts", "phone_verification_code_hash")
    op.drop_column("client_accounts", "phone_verified")
