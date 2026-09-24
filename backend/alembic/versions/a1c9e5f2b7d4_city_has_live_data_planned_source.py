"""city has_live_data + planned_data_source

Revision ID: a1c9e5f2b7d4
Revises: fb7c98e7340a
Create Date: 2026-09-25 00:00:00.000000

Session 018 (user request): the header's city selector needs to know
which city actually has a live data connector (Toulouse, today) versus
which are real, selectable, map-recenterable cities with no connector yet
— so the dashboard can show an honest "no live data" state instead of
silently reusing Toulouse's numbers under a different city's label.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9e5f2b7d4'
down_revision: Union[str, None] = 'fb7c98e7340a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'cities',
        sa.Column('has_live_data', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'cities',
        sa.Column('planned_data_source', sa.String(length=160), nullable=True),
    )
    # The one city seeded before this migration (Toulouse) is the real,
    # already-ingested demo city — mark it explicitly rather than leaving
    # every pre-existing row at the column default of false.
    op.execute("UPDATE cities SET has_live_data = true WHERE label_en = 'Toulouse'")


def downgrade() -> None:
    op.drop_column('cities', 'planned_data_source')
    op.drop_column('cities', 'has_live_data')
