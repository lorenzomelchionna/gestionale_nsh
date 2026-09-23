"""add position to collaborators

Revision ID: c4e7a2d91b05
Revises: f8a2e916c4d3
Create Date: 2026-09-23

L'ordine delle colonne nel calendario, deciso dal salone invece che dal
database. Prima l'elenco non aveva nessun ORDER BY: usciva nell'ordine fisico
delle righe, che Postgres non garantisce e che un UPDATE può cambiare.

Il backfill segue l'id, cioè l'ordine che si vedeva di fatto fino a oggi: il
rilascio da solo non sposta niente, l'ordine nuovo lo sceglie chi usa il
gestionale. Qui non c'è nessun collaboratore nominato di proposito — questa
migration gira anche su database vuoti, e i dati di un salone non stanno
nella storia dello schema.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e7a2d91b05"
down_revision: Union[str, None] = "f8a2e916c4d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "collaborators",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE collaborators c
        SET position = ordinati.n
        FROM (
            SELECT id, row_number() OVER (ORDER BY id) - 1 AS n
            FROM collaborators
        ) AS ordinati
        WHERE c.id = ordinati.id
        """
    )
    op.alter_column("collaborators", "position", server_default=None)


def downgrade() -> None:
    op.drop_column("collaborators", "position")
