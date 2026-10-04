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
    has_live_data: bool
    planned_data_source: str | None = None
    connector_status: str = "none"
    is_primary: bool = False

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
