"""drop max_advance_days from booking_config

Le clienti prenotano senza tetto in avanti (2026-11-20): con 30 giorni, a fine
novembre la settimana di Natale non era prenotabile. Il campo non lo legge più
nessuno, quindi se ne va invece di restare lì a sembrare un'impostazione viva.

Revision ID: d8f3a6c21b57
Revises: c4e9b1f7a2d6
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8f3a6c21b57"
down_revision: Union[str, None] = "c4e9b1f7a2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("booking_config", "max_advance_days")


def downgrade() -> None:
    # Il valore che c'era prima non si recupera: si torna al default di sempre.
    op.add_column(
        "booking_config",
        sa.Column("max_advance_days", sa.Integer(), nullable=False, server_default="30"),
    )
