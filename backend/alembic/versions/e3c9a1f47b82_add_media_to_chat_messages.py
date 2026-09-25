"""add media to chat_messages

Revision ID: e3c9a1f47b82
Revises: d7b2e5a91c30
Create Date: 2026-09-25

Gli allegati dei messaggi WhatsApp in arrivo. Fino a oggi il webhook salvava
un messaggio solo se aveva del testo: una foto o un vocale senza didascalia
andavano persi per intero. Colonna nuova e nullable, niente backfill qui — i
messaggi persi si recuperano da Twilio con `scripts/recupera_allegati_chat.py`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3c9a1f47b82"
down_revision: Union[str, None] = "d7b2e5a91c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("media", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "media")
