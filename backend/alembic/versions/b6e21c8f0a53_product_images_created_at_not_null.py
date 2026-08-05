"""product_images.created_at NOT NULL, come dice il modello

Revision ID: b6e21c8f0a53
Revises: a1f39d7c4b28
Create Date: 2026-08-05

Deriva fra modello e database trovata con `alembic check`: il modello
dichiara `created_at` non nullabile (`Mapped[datetime]` senza Optional),
la migration delle foto la creò nullabile.

Senza conseguenze pratiche — `server_default=now()` l'ha sempre riempita —
ma finché resta, ogni `alembic revision --autogenerate` si porta dietro
questa stessa operazione come modifica spuria, e chi la vede non sa dire
se sia una deriva vecchia o qualcosa che ha appena rotto lui.

La CI esegue `upgrade head`, non `check`, quindi non se ne sarebbe accorta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6e21c8f0a53"
down_revision: Union[str, None] = "a1f39d7c4b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # In teoria non serve: il default riempie la colonna da sempre. In pratica
    # `SET NOT NULL` fallisce su una sola riga nulla e manderebbe giù il
    # servizio all'avvio, visto che le migration girano nello startCommand.
    op.execute(
        "UPDATE product_images SET created_at = now() WHERE created_at IS NULL"
    )
    op.alter_column(
        "product_images",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_server_default=sa.text("now()"),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "product_images",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_server_default=sa.text("now()"),
        nullable=True,
    )
