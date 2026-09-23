"""P1 — environmental data sources, stations, measurements, and the Command
Center's KPI summary. All read-only; ingestion happens in the background
scheduler (`app.core.scheduler`) and the demo seed/reset script."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.environmental import DataSource, Measurement, MeasurementVariable, Station
from app.models.user import User
from app.schemas.environmental import (
    EnvironmentalSummaryOut,
    LatestReadingOut,
    SourceHealthOut,
    StationOut,
    StationTimeseriesOut,
    TimeseriesPoint,
    TimeseriesSeries,
)
from app.services.ingestion_service import compute_source_health

router = APIRouter()


@router.get("/sources", response_model=list[SourceHealthOut])
def list_sources(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("DATA_SOURCES", "VIEW")),
) -> list[SourceHealthOut]:
    sources = db.execute(select(DataSource).order_by(DataSource.name)).scalars().all()
    now = datetime.now(timezone.utc)
    return [
        SourceHealthOut(
            id=s.id,
            code=s.code,
            name=s.name,
            provider=s.provider,
            kind=s.kind,
            is_active=s.is_active,
            license=s.license,
            homepage_url=s.homepage_url,
            health=compute_source_health(s, now).value,
            last_attempt_at=s.last_attempt_at,
            last_success_at=s.last_success_at,
            consecutive_failures=s.consecutive_failures,
            last_error_message=s.last_error_message,
        )
        for s in sources
    ]


def _latest_readings_by_station(db: Session, station_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[LatestReadingOut]]:
    if not station_ids:
        return {}
    # DISTINCT ON (Postgres): the single most recent row per (station, variable).
    rows = db.execute(
        select(Measurement)
        .where(Measurement.station_id.in_(station_ids))
        .order_by(Measurement.station_id, Measurement.variable, Measurement.observed_at.desc())
        .distinct(Measurement.station_id, Measurement.variable)
    ).scalars().all()
    out: dict[uuid.UUID, list[LatestReadingOut]] = {}
    for row in rows:
        out.setdefault(row.station_id, []).append(
            LatestReadingOut(variable=row.variable, value=row.value, unit=row.unit, observed_at=row.observed_at)
        )
    return out


@router.get("/stations", response_model=list[StationOut])
def list_stations(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("MAP", "VIEW")),
) -> list[StationOut]:
    rows = db.execute(
        select(Station, DataSource, ST_X(Station.geom), ST_Y(Station.geom))
        .join(DataSource, DataSource.id == Station.data_source_id)
        .order_by(Station.name)
    ).all()
    station_ids = [row[0].id for row in rows]
    latest_by_station = _latest_readings_by_station(db, station_ids)
    now = datetime.now(timezone.utc)

    return [
        StationOut(
            id=station.id,
            external_code=station.external_code,
            name=station.name,
            kind=station.kind,
            city=station.city,
            river_name=station.river_name,
            lon=lon,
            lat=lat,
            source_code=source.code,
            source_health=compute_source_health(source, now).value,
            latest=latest_by_station.get(station.id, []),
        )
        for station, source, lon, lat in rows
    ]


@router.get("/stations/{station_id}/timeseries", response_model=StationTimeseriesOut)
def station_timeseries(
    station_id: uuid.UUID,
    hours: int = Query(default=48, ge=1, le=168),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("MAP", "VIEW")),
) -> StationTimeseriesOut:
    station = db.get(Station, station_id)
    if station is None:
        raise NotFoundError(message="Station not found")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(
        select(Measurement)
        .where(Measurement.station_id == station_id, Measurement.observed_at >= since)
        .order_by(Measurement.variable, Measurement.observed_at)
    ).scalars().all()

    series_by_variable: dict[str, TimeseriesSeries] = {}
    for row in rows:
        series = series_by_variable.get(row.variable)
        if series is None:
            series = TimeseriesSeries(variable=row.variable, unit=row.unit, points=[])
            series_by_variable[row.variable] = series
        series.points.append(TimeseriesPoint(value=row.value, observed_at=row.observed_at))

    return StationTimeseriesOut(
        station_id=station.id,
        station_name=station.name,
        series=list(series_by_variable.values()),
    )


@router.get("/summary", response_model=EnvironmentalSummaryOut)
def environmental_summary(
    # P2.1 (D017): the Command Center's chart time-range selector drives this
    # directly — same bounds as station_timeseries's `hours` param, for
    # consistency. Defaults to 48h (the prior hardcoded window) so existing
    # callers/tests that omit it keep the exact previous behavior.
    hours: int = Query(default=48, ge=1, le=168),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("DASHBOARD", "VIEW")),
) -> EnvironmentalSummaryOut:
    now = datetime.now(timezone.utc)

    sources = db.execute(select(DataSource)).scalars().all()
    active_sources = sum(1 for s in sources if s.is_active)
    fresh_sources = sum(1 for s in sources if compute_source_health(s, now).value == "fresh")
    monitored_stations = db.execute(select(func.count(Station.id))).scalar_one()

    def _latest(variable: MeasurementVariable) -> LatestReadingOut | None:
        row = db.execute(
            select(Measurement)
            .where(Measurement.variable == variable.value)
            .order_by(Measurement.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return LatestReadingOut(variable=row.variable, value=row.value, unit=row.unit, observed_at=row.observed_at)

    def _trend(variable: MeasurementVariable, window_hours: int) -> tuple[list[float], list[str]]:
        since = now - timedelta(hours=window_hours)
        rows = db.execute(
            select(Measurement)
            .where(Measurement.variable == variable.value, Measurement.observed_at >= since)
            .order_by(Measurement.observed_at)
        ).scalars().all()
        return [r.value for r in rows], [r.observed_at.isoformat() for r in rows]

    water_trend_values, water_trend_ts = _trend(MeasurementVariable.WATER_LEVEL_MM, hours)
    precip_trend_values, precip_trend_ts = _trend(MeasurementVariable.PRECIPITATION_MM, hours)
    temp_trend_values, temp_trend_ts = _trend(MeasurementVariable.TEMPERATURE_C, hours)
    humidity_trend_values, humidity_trend_ts = _trend(MeasurementVariable.HUMIDITY_PERCENT, hours)
    # P2.1: 4 more free Open-Meteo variables — same latest+trend pattern.
    wind_speed_trend_values, wind_speed_trend_ts = _trend(MeasurementVariable.WIND_SPEED_KMH, hours)
    wind_direction_trend_values, wind_direction_trend_ts = _trend(MeasurementVariable.WIND_DIRECTION_DEG, hours)
    surface_pressure_trend_values, surface_pressure_trend_ts = _trend(MeasurementVariable.SURFACE_PRESSURE_HPA, hours)
    uv_index_trend_values, uv_index_trend_ts = _trend(MeasurementVariable.UV_INDEX, hours)

    # `precipitation_24h_total_mm` is a deliberate exception: always the
    # actual last-24h rainfall total, independent of the selected chart
    # range, so it does not use the `hours`-driven trend above.
    precip_24h_values, _ = _trend(MeasurementVariable.PRECIPITATION_MM, 24)
    precipitation_24h_total = round(sum(precip_24h_values), 1) if precip_24h_values else None

    return EnvironmentalSummaryOut(
        monitored_stations=monitored_stations,
        active_sources=active_sources,
        fresh_sources=fresh_sources,
        trend_window_hours=hours,
        water_level=_latest(MeasurementVariable.WATER_LEVEL_MM),
        water_level_trend=water_trend_values,
        water_level_trend_timestamps=water_trend_ts,
        precipitation_24h_total_mm=precipitation_24h_total,
        precipitation_trend=precip_trend_values,
        precipitation_trend_timestamps=precip_trend_ts,
        temperature=_latest(MeasurementVariable.TEMPERATURE_C),
        temperature_trend=temp_trend_values,
        temperature_trend_timestamps=temp_trend_ts,
        humidity=_latest(MeasurementVariable.HUMIDITY_PERCENT),
        humidity_trend=humidity_trend_values,
        humidity_trend_timestamps=humidity_trend_ts,
        wind_speed=_latest(MeasurementVariable.WIND_SPEED_KMH),
        wind_speed_trend=wind_speed_trend_values,
        wind_speed_trend_timestamps=wind_speed_trend_ts,
        wind_direction=_latest(MeasurementVariable.WIND_DIRECTION_DEG),
        wind_direction_trend=wind_direction_trend_values,
        wind_direction_trend_timestamps=wind_direction_trend_ts,
        surface_pressure=_latest(MeasurementVariable.SURFACE_PRESSURE_HPA),
        surface_pressure_trend=surface_pressure_trend_values,
        surface_pressure_trend_timestamps=surface_pressure_trend_ts,
        uv_index=_latest(MeasurementVariable.UV_INDEX),
        uv_index_trend=uv_index_trend_values,
        uv_index_trend_timestamps=uv_index_trend_ts,
    )
