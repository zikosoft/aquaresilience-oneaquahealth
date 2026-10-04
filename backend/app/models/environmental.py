"""P1 — environmental data foundation: sources, stations, measurements.

Design notes:
- `DataSource` is one configured external connector (e.g. "Hub'Eau Hydrometrie
  Toulouse", "Open-Meteo Toulouse"). Its own health/freshness fields let the
  ingestion job and the API report per-source status without any separate
  health table.
- `Station` is a physical monitoring point (PostGIS `POINT`, SRID 4326 /
  WGS84 — matches GeoJSON and MapLibre's default expectations directly, no
  reprojection needed).
- `Measurement` is a single time-series reading. The
  (station_id, variable, observed_at) unique constraint is the idempotency
  mechanism required by the P1 gate: re-ingesting the same source window
  twice never creates duplicate rows, it just no-ops on conflict.
- Per D006 (locked decision), the platform never shows a raw LIVE/CACHED/
  REPLAY badge in the UI. `is_backfill` exists purely so the deterministic
  demo seed can distinguish its own synthetic history from live-ingested
  readings for internal bookkeeping (e.g. reset) — it is never surfaced to
  the frontend as a data-provenance label; freshness (fresh/stale/degraded)
  is the only status concept exposed to users.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.geography import City


class DataSourceProvider(StrEnum):
    HUBEAU_HYDROMETRIE = "hubeau_hydrometrie"
    OPEN_METEO = "open_meteo"
    NVE_HYDAPI = "nve_hydapi"
    EHYD = "ehyd"
    WATERINFO_BE = "waterinfo_be"


class DataSourceKind(StrEnum):
    HYDROLOGY = "hydrology"
    WEATHER = "weather"


class StationKind(StrEnum):
    RIVER_GAUGE = "river_gauge"
    WEATHER_POINT = "weather_point"


class MeasurementVariable(StrEnum):
    WATER_LEVEL_MM = "water_level_mm"
    PRECIPITATION_MM = "precipitation_mm"
    SOIL_MOISTURE_RATIO = "soil_moisture_ratio"
    TEMPERATURE_C = "temperature_c"
    HUMIDITY_PERCENT = "humidity_percent"
    # P2.1: 4 more free Open-Meteo hourly variables (no new source/key),
    # reaching the requested 8-tile Command Center KPI row.
    WIND_SPEED_KMH = "wind_speed_kmh"
    WIND_DIRECTION_DEG = "wind_direction_deg"
    SURFACE_PRESSURE_HPA = "surface_pressure_hpa"
    UV_INDEX = "uv_index"


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One configured external connector and its running health state."""

    __tablename__ = "data_sources"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    license: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    homepage_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Expected cadence, used to judge freshness independently of when the
    # scheduler actually last ran (e.g. Hub'Eau publishes ~every 5 min).
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    # A source counts as "stale" past this many missed intervals worth of
    # silence, and "degraded" once ingestion has been actively failing.
    stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)

    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    city_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True
    )
    # Same write-only-secret pattern as AIProviderConfig.encrypted_api_key
    # (app/models/settings.py): encrypted at rest via
    # app.core.security.encrypt_secret/decrypt_secret, never returned to the
    # frontend once saved. Null for keyless connectors (Hub'Eau, Open-Meteo,
    # eHYD, Waterinfo.be without a registered token).
    encrypted_api_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    stations: Mapped[list["Station"]] = relationship(back_populates="data_source", cascade="all, delete-orphan")
    city: Mapped["City | None"] = relationship()

    @property
    def is_key_configured(self) -> bool:
        return bool(self.encrypted_api_key)


class Station(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical monitoring point belonging to one data source."""

    __tablename__ = "stations"
    __table_args__ = (UniqueConstraint("data_source_id", "external_code", name="uq_station_source_external_code"),)

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    river_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # WGS84 point, srid 4326 — directly usable by MapLibre/GeoJSON with no
    # reprojection.
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    data_source: Mapped["DataSource"] = relationship(back_populates="stations")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="station", cascade="all, delete-orphan")


class Measurement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single time-series reading. Idempotent on (station, variable, observed_at)."""

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("station_id", "variable", "observed_at", name="uq_measurement_station_variable_time"),
    )

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    variable: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Internal bookkeeping only — never exposed as a UI provenance badge (D006).
    is_backfill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    station: Mapped["Station"] = relationship(back_populates="measurements")
