"""add color to services

Revision ID: f5a8c2d64e19
Revises: e3c9a1f47b82
Create Date: 2026-09-29

Il colore di ogni servizio nel calendario, scelto dall'admin. Nullable e
senza valore iniziale: finché nessuno lo sceglie, il calendario resta com'era.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a8c2d64e19"
down_revision: Union[str, None] = "e3c9a1f47b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("services", sa.Column("color", sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "color")
