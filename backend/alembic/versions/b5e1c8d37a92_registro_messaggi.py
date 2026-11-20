"""registro_messaggi replaces communications

`communications` was in the initial schema and no code ever wrote to it. The
message log takes its place, with the columns a log actually needs: type,
recipient, appointment, provider id for delivery status, error.

Revision ID: b5e1c8d37a92
Revises: a3b7e2c9d140
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5e1c8d37a92"
down_revision: Union[str, None] = "a3b7e2c9d140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("communications")
    sa.Enum(name="communicationtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="communicationstatus").drop(op.get_bind(), checkfirst=True)

    op.create_table(
        "registro_messaggi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creato_il", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("canale", sa.String(length=16), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("destinatario", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("oggetto", sa.String(length=300), nullable=True),
        sa.Column("testo", sa.Text(), nullable=True),
        sa.Column("formato", sa.String(length=20), nullable=True),
        sa.Column("stato", sa.String(length=20), nullable=False),
        sa.Column("errore", sa.Text(), nullable=True),
        sa.Column("id_fornitore", sa.String(length=120), nullable=True),
        sa.Column("stato_aggiornato_il", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registro_messaggi_creato_il", "registro_messaggi", ["creato_il"])
    op.create_index("ix_registro_messaggi_client_id", "registro_messaggi", ["client_id"])
    op.create_index("ix_registro_messaggi_id_fornitore", "registro_messaggi", ["id_fornitore"])


def downgrade() -> None:
    op.drop_index("ix_registro_messaggi_id_fornitore", table_name="registro_messaggi")
    op.drop_index("ix_registro_messaggi_client_id", table_name="registro_messaggi")
    op.drop_index("ix_registro_messaggi_creato_il", table_name="registro_messaggi")
    op.drop_table("registro_messaggi")
    op.create_table(
        "communications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.Enum("email", "sms", "whatsapp", name="communicationtype"), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("sent", "failed", "pending", name="communicationstatus"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
