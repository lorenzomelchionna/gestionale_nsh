"""fornitore sui prodotti

Revision ID: e4a7c02b91d5
Revises: c8b3f5d1a742
Create Date: 2026-08-04

Colonna nullable senza default: un prodotto già a magazzino non ha un
fornitore noto, e inventarne uno sarebbe peggio che lasciare il campo
vuoto. NULL qui significa "non lo sappiamo", non "nessuno".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e4a7c02b91d5"
down_revision: Union[str, None] = "c8b3f5d1a742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("supplier", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "supplier")
