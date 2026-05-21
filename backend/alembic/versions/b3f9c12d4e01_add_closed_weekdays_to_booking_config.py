"""add closed_weekdays to booking_config

Revision ID: b3f9c12d4e01
Revises: a08f71ad09bf
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa

revision = 'b3f9c12d4e01'
down_revision = 'a08f71ad09bf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'booking_config',
        sa.Column('closed_weekdays', sa.JSON(), nullable=False, server_default='[0, 1]'),
    )


def downgrade() -> None:
    op.drop_column('booking_config', 'closed_weekdays')
