"""data source city_id + encrypted_api_key

Revision ID: c2f4a9b81e03
Revises: a1c9e5f2b7d4
Create Date: 2026-09-25 10:30:00.000000

The two pre-existing sources (Hub'Eau + Open-Meteo, both Toulouse) are
backfilled to Toulouse's City row here for immediate correctness;
`ingestion_service.get_or_create_data_source` also self-heals this same
sync on every ingestion tick going forward, so no city is ever stuck
unlinked just because a migration ran before its City row existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c2f4a9b81e03'
down_revision: Union[str, None] = 'a1c9e5f2b7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'data_sources',
        sa.Column('city_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_data_sources_city_id_cities',
        'data_sources',
        'cities',
        ['city_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.add_column(
        'data_sources',
        sa.Column('encrypted_api_key', sa.String(length=1024), nullable=True),
    )
    # Backfill the 2 existing Toulouse sources immediately (if the
    # Toulouse city row already exists at migration time — it does on
    # every real deployment, since seed_geography runs before this).
    op.execute(
        """
        UPDATE data_sources
        SET city_id = cities.id
        FROM cities
        WHERE cities.label_en = 'Toulouse'
          AND data_sources.code IN ('hubeau_hydrometrie_toulouse_garonne', 'open_meteo_toulouse')
          AND data_sources.city_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column('data_sources', 'encrypted_api_key')
    op.drop_constraint('fk_data_sources_city_id_cities', 'data_sources', type_='foreignkey')
    op.drop_column('data_sources', 'city_id')
