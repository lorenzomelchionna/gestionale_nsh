"""add closed_dates to booking_config

Chiusure del salone per data (ferie, ponti, festività in cui non apre),
accanto ai giorni chiusi della settimana. Vuote all'inizio: nessuna festività
è chiusa di default.

Revision ID: a3b7e2c9d140
Revises: c4e9b1f7a2d6
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b7e2c9d140"
down_revision: Union[str, None] = "c4e9b1f7a2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "booking_config",
        sa.Column("closed_dates", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("booking_config", "closed_dates")
