"""add email verification to client_accounts

Revision ID: d7a1c93f2b48
Revises: cb5f8e06a8a7
Create Date: 2026-07-29

Accounts that already exist predate verification, so they are marked verified
rather than being locked out of an app they were already using. New rows default
to false and earn it by entering the emailed code.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a1c93f2b48"
down_revision: Union[str, None] = "cb5f8e06a8a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default fills the existing rows in place; without it the NOT NULL
    # would be rejected on any table that already holds accounts.
    op.add_column(
        "client_accounts",
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "client_accounts",
        sa.Column("verification_code_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "client_accounts",
        sa.Column("verification_expires", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_accounts",
        sa.Column(
            "verification_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # Grandfather everyone who signed up before this existed.
    op.execute("UPDATE client_accounts SET email_verified = true")

    # The default was only needed to backfill; new rows get their value from the
    # application, which creates them unverified.
    op.alter_column("client_accounts", "email_verified", server_default=None)
    op.alter_column("client_accounts", "verification_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("client_accounts", "verification_attempts")
    op.drop_column("client_accounts", "verification_expires")
    op.drop_column("client_accounts", "verification_code_hash")
    op.drop_column("client_accounts", "email_verified")
