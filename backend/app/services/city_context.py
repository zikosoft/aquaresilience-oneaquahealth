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
    """Session 020: the platform's one designated 'primary' city for the
    features that are still genuinely global/singleton rather than
    per-city — the shared AI Situation Brief (SituationBrief has no city
    column, Master Spec §19: "one shared stored brief for all users"), the
    background scheduler's warning evaluation, and the Early Warnings
    lifecycle itself (Warning has no city column either). Toulouse is that
    city: the platform's original demo city and this hackathon's Track 6
    subject (Toulouse Métropole). Falls back to None (today's unscoped
    global-scan behavior in risk_engine._scope_to_city) if that row is ever
    missing, rather than erroring out a scheduler tick or a brief refresh —
    should never happen in practice since seed_geography always creates it.
    Making Early Warnings/the AI brief genuinely per-city is a larger,
    separate redesign (multiplying LLM calls and warning rows per live
    city) — out of scope for this pass; see the Settings/AI Intelligence
    docs for the current single-brief rationale."""
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
