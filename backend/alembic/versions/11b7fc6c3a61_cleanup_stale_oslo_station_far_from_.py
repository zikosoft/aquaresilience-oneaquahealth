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
    # Session 022 fix (user report): NVE HydAPI's station-selection logic
    # (app/services/connectors/nve_hydapi.py::_find_station) used to pick
    # the first active, water-level-capable station NVE's API happened to
    # list for CouncilName=Oslo — a whole municipality reaching well past
    # downtown (Ellingsrud, Groruddalen, ...) — instead of the one closest
    # to the city's own reference point (the same point the weather
    # connector uses). That selection logic is now fixed, but a Station
    # row's geom is only ever set once, at creation
    # (ingestion_service._get_or_create_station), and never updated on
    # later ticks — so a station already ingested under the old, arbitrary
    # pick would otherwise stay stuck far from the city forever, even
    # after the connector fix.
    #
    # This runs on every deploy (alembic upgrade head, same as a fresh
    # install) and only ever removes a Station row for the Oslo hydrology
    # source if it is clearly far (>~5km, in degrees) from Oslo's own
    # reference point (10.7522, 59.9139) — the exact same distance check
    # the fixed connector now applies when choosing a station. It is a
    # safe no-op wherever that doesn't apply: a brand-new environment with
    # no nve_hydapi_oslo data source yet, or one where the station is
    # already correctly placed. Removing it here (rather than a one-off
    # manual SQL step) means it self-heals in every environment —
    # including prod — the next time migrations run, with no manual DB
    # access required. The next scheduler tick recreates the station with
    # the corrected, closest-match selection; its measurements cascade-
    # delete with it (Measurement.station_id is ON DELETE CASCADE) and are
    # likewise reingested.
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
