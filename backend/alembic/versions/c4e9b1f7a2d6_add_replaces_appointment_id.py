"""add replaces_appointment_id to appointments

Revision ID: c4e9b1f7a2d6
Revises: a7d3c9e15f42
Create Date: 2026-10-13

La richiesta di modifica di un appuntamento confermato, fatta dalla cliente
dal portale: è un appuntamento nuovo «in attesa» che punta a quello che
sostituirebbe. Il vecchio resta confermato finché il salone non accetta;
accettando, il vecchio viene annullato. Nullable e vuoto per tutto quello che
esiste già. SET NULL: cancellare l'originale non deve portarsi via la storia
della richiesta.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e9b1f7a2d6"
down_revision: Union[str, None] = "a7d3c9e15f42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "replaces_appointment_id", sa.Integer(),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_appointments_replaces_appointment_id", "appointments", ["replaces_appointment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_replaces_appointment_id", table_name="appointments")
    op.drop_column("appointments", "replaces_appointment_id")
