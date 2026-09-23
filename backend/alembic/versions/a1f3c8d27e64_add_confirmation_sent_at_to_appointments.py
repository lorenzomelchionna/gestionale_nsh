"""add confirmation_sent_at to appointments

Revision ID: a1f3c8d27e64
Revises: c4e7a2d91b05
Create Date: 2026-09-23

Quando la conferma è partita davvero. Serve al promemoria, che non deve
arrivare nella prima ora dopo la conferma: `created_at` non basta, perché le
prenotazioni online nascono «in attesa» e vengono confermate più tardi.

Nessun backfill: per gli appuntamenti che esistono già non si sa quando sia
partita la conferma, e `NULL` vuol dire «nessuna conferma recente da
rispettare» — il comportamento giusto per appuntamenti creati prima di oggi.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f3c8d27e64"
down_revision: Union[str, None] = "c4e7a2d91b05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("confirmation_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "confirmation_sent_at")
