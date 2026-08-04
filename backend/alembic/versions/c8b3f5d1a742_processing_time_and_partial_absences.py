"""tempo di posa sui servizi, assenze a ore

Revision ID: c8b3f5d1a742
Revises: f2c4a91b7e30
Create Date: 2026-08-04

Entrambe le aggiunte sono retrocompatibili per costruzione: i default
riproducono esattamente il comportamento precedente, quindi le righe che
esistono già non cambiano significato.

- `services.processing_slots = 0` → nessuna posa, collaboratore occupato
  per tutta la durata, come prima.
- `absences.start_time / end_time = NULL` → assenza a giornata intera,
  come prima.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8b3f5d1a742"
down_revision: Union[str, None] = "f2c4a91b7e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default oltre al default Python: le righe esistenti vanno
    # riempite adesso, e senza di esso la colonna NOT NULL non si può
    # aggiungere a una tabella già popolata.
    op.add_column(
        "services",
        sa.Column("processing_slots", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "services",
        sa.Column(
            "slots_before_processing", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column("absences", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("absences", sa.Column("end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("absences", "end_time")
    op.drop_column("absences", "start_time")
    op.drop_column("services", "slots_before_processing")
    op.drop_column("services", "processing_slots")
