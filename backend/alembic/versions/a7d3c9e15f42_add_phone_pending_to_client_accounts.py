"""add phone_pending to client_accounts

Revision ID: a7d3c9e15f42
Revises: f5a8c2d64e19
Create Date: 2026-10-06

Il numero corretto dalla schermata del codice WhatsApp, in attesa che il
codice lo dimostri. Nullable e vuoto per tutti: finché nessuno corregge
niente, il codice parte al numero della scheda come prima.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3c9e15f42"
down_revision: Union[str, None] = "f5a8c2d64e19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_accounts",
        sa.Column("phone_pending", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_accounts", "phone_pending")
