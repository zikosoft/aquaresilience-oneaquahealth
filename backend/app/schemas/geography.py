from __future__ import annotations

import uuid

from pydantic import BaseModel


class CityOut(BaseModel):
    id: uuid.UUID
    label_en: str
    label_fr: str
    label_es: str
    country_iso2: str
    default_lon: float
    default_lat: float
    default_zoom: int
    # Session 018: whether this city has an actual ingested data connector
    # (only Toulouse today) vs. is a real, selectable-but-not-yet-connected
    # consortium city — see app/models/geography.py's module docstring.
    has_live_data: bool
    planned_data_source: str | None = None
    # Session 020 (user request): 3-tier signal for the header's city
    # selector, distinct from the plain has_live_data bool — "live" (real
    # ingested data), "pending" (a connector is registered and has at least
    # attempted a fetch — e.g. Oslo/NVE before its API key is configured —
    # so it just needs a key/time, not code), or "none" (no connector has
    # ever run for this city at all — e.g. Athens/Barcelona/Naples/Holon,
    # and Coimbra which was explicitly not integrated this round). Computed
    # from whether any DataSource row exists for the city, never hardcoded
    # per-city in the frontend — see app/api/v1/geography.py.
    connector_status: str = "none"

    model_config = {"from_attributes": True}


class MapConfigOut(BaseModel):
    """Effective map configuration for every role that can view the map —
    the Settings > Map tab's tile-provider choice plus the city defaults,
    combined so `ResilienceMap.vue` needs only one MAP:VIEW-gated call."""

    tile_provider: str
    # P4.1: 0-100, Settings > Map-configurable opacity for the risk-level
    # circle layer around the river gauge station.
    risk_layer_opacity: int
    cities: list[CityOut]
