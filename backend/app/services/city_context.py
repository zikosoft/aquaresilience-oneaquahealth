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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.geography import City


def get_primary_city_id(db: Session) -> uuid.UUID | None:
    """Session 020: the platform's one designated 'primary' city — still
    used as the default/fallback for features that remain genuinely
    global/singleton: the background scheduler's own warning evaluation and
    the Early Warnings lifecycle itself (Warning has no city column yet).
    Toulouse is that city: the platform's original demo city and this
    hackathon's Track 6 subject (Toulouse Métropole). Falls back to None
    (today's unscoped global-scan behavior in risk_engine._scope_to_city) if
    that row is ever missing, rather than erroring out a scheduler tick or a
    brief refresh — should never happen in practice since seed_geography
    always creates it.

    Session 022 (user request): the AI Situation Brief is no longer
    pinned here — it now follows whichever city is selected/rotated to
    (see `app.services.intelligence_service.generate_situation_brief` and
    `pick_next_scheduled_city_id`), falling back to this primary city only
    when no explicit city is given. Making Early Warnings genuinely
    per-city too (it still isn't) is a separate, larger change — Warning
    has no city column at all yet."""
    city = db.execute(select(City).where(City.label_en == "Toulouse")).scalar_one_or_none()
    return city.id if city else None


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
