"""cleanup stale oslo station far from city center

Revision ID: 11b7fc6c3a61
Revises: c2f4a9b81e03
Create Date: 2026-10-03 19:33:59.692131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11b7fc6c3a61'
down_revision: Union[str, None] = 'c2f4a9b81e03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM stations
        WHERE id IN (
            SELECT s.id
            FROM stations s
            JOIN data_sources ds ON ds.id = s.data_source_id
            WHERE ds.code = 'nve_hydapi_oslo'
              AND (POWER(ST_X(s.geom) - 10.7522, 2) + POWER(ST_Y(s.geom) - 59.9139, 2)) > POWER(0.05, 2)
        )
        """
    )


def downgrade() -> None:
    # Irreversible, deliberately: this is a one-time data cleanup, not a
    # schema change. A removed stale station is recreated automatically by
    # the next ingestion tick with corrected coordinates — reversing this
    # migration would mean re-fabricating the exact old (wrong) row, which
    # is never the right direction to go.
    pass
