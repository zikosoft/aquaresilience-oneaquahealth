from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SourceHealthOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    provider: str
    kind: str
    is_active: bool
    license: str
    homepage_url: str
    health: str  # fresh | stale | degraded
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    last_error_message: str | None

    model_config = {"from_attributes": True}


class LatestReadingOut(BaseModel):
    variable: str
    value: float
    unit: str
    observed_at: datetime


class StationOut(BaseModel):
    id: uuid.UUID
    external_code: str
    name: str
    kind: str
    city: str
    river_name: str | None
    lon: float
    lat: float
    source_code: str
    source_health: str
    latest: list[LatestReadingOut]


class TimeseriesPoint(BaseModel):
    value: float
    observed_at: datetime


class TimeseriesSeries(BaseModel):
    variable: str
    unit: str
    points: list[TimeseriesPoint]


class StationTimeseriesOut(BaseModel):
    station_id: uuid.UUID
    station_name: str
    series: list[TimeseriesSeries]


class EnvironmentalSummaryOut(BaseModel):
    """Command Center KPI summary: latest reading + trend per key variable.

    P2.1: the trend window is caller-selectable (D017, `?hours=`), so field
    names dropped their earlier hardcoded "_24h" suffix — `trend_window_hours`
    echoes back the effective window actually used, for chart titles.
    `precipitation_24h_total_mm` is a deliberate exception: it is a genuinely
    fixed 24h "daily rainfall" figure, independent of the selected chart
    range.
    """

    monitored_stations: int
    active_sources: int
    fresh_sources: int
    trend_window_hours: int
    water_level: LatestReadingOut | None
    water_level_trend: list[float]
    water_level_trend_timestamps: list[str]
    precipitation_24h_total_mm: float | None
    precipitation_trend: list[float]
    precipitation_trend_timestamps: list[str]
    temperature: LatestReadingOut | None
    temperature_trend: list[float]
    temperature_trend_timestamps: list[str]
    humidity: LatestReadingOut | None
    humidity_trend: list[float]
    humidity_trend_timestamps: list[str]
    # P2.1: 4 more free Open-Meteo hourly variables — same trend pattern.
    wind_speed: LatestReadingOut | None
    wind_speed_trend: list[float]
    wind_speed_trend_timestamps: list[str]
    wind_direction: LatestReadingOut | None
    wind_direction_trend: list[float]
    wind_direction_trend_timestamps: list[str]
    surface_pressure: LatestReadingOut | None
    surface_pressure_trend: list[float]
    surface_pressure_trend_timestamps: list[str]
    uv_index: LatestReadingOut | None
    uv_index_trend: list[float]
    uv_index_trend_timestamps: list[str]
