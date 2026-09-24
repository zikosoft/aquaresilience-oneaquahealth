"""Session 018 — shared "which city, does it have live data" guard.

The header's city selector (see `app/api/v1/geography.py`) lets an operator
pick any of the 9 consortium cities, but only Toulouse has an actual
ingested connector. Every dashboard-facing endpoint that would otherwise
silently compute Toulouse's real numbers under a different city's label
calls `resolve_city` and, when `has_data` is False, returns its normal
response type with `data_available=False` instead — same object shape for
the frontend either way (per the user's explicit instruction), just empty.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.geography import City


def resolve_city(db: Session, city_id: uuid.UUID | None) -> tuple[City | None, bool]:
    """Returns (city_or_none, has_data).

    No city_id (legacy/omitted callers, e.g. existing tests): unchanged
    behavior, has_data=True. An unrecognized city_id degrades the same way
    rather than erroring a dashboard load over a stale selection.
    """
    if city_id is None:
        return None, True
    city = db.get(City, city_id)
    if city is None:
        return None, True
    return city, city.has_live_data
