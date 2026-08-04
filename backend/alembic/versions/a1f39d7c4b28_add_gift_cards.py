"""buoni regalo

Revision ID: a1f39d7c4b28
Revises: e4a7c02b91d5
Create Date: 2026-08-05

Due tabelle e un valore in più sull'enum dei pagamenti.

`ALTER TYPE ... ADD VALUE` va eseguito fuori dalla transazione della
migration: Postgres non permette di usare un valore aggiunto nella stessa
transazione che lo crea, e su versioni precedenti alla 12 rifiuta proprio
l'istruzione dentro un blocco. `autocommit_block()` la isola, così la
migration si applica identica ovunque invece che solo sul Postgres di qui.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1f39d7c4b28"
down_revision: Union[str, None] = "e4a7c02b91d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE paymenttype ADD VALUE IF NOT EXISTS 'gift_card'")

    op.create_table(
        "gift_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("initial_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("balance", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("recipient_name", sa.String(length=200), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("purchaser_client_id", sa.Integer(), nullable=True),
        sa.Column("purchaser_name", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["purchaser_client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gift_cards_code"), "gift_cards", ["code"], unique=True)

    op.create_table(
        "gift_card_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gift_card_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        # CASCADE: i riscatti non hanno vita propria, sono la storia di quella
        # card. ON DELETE SET NULL sull'appuntamento invece sì — cancellare un
        # appuntamento non deve cancellare la traccia di un credito speso.
        sa.ForeignKeyConstraint(["gift_card_id"], ["gift_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gift_card_redemptions_gift_card_id"),
        "gift_card_redemptions", ["gift_card_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gift_card_redemptions_gift_card_id"), table_name="gift_card_redemptions")
    op.drop_table("gift_card_redemptions")
    op.drop_index(op.f("ix_gift_cards_code"), table_name="gift_cards")
    op.drop_table("gift_cards")
    # Il valore sull'enum resta: Postgres non sa togliere un valore da un tipo
    # esistente, e ricreare il tipo vorrebbe dire riscrivere `payments`. Un
    # valore in più inutilizzato non fa danno, un downgrade che riscrive la
    # tabella dei pagamenti sì.
