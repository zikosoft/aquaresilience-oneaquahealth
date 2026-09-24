"""Deterministic environmental demo seed/reset (P1).

Guarantees the Command Center and map are never empty — not on a brand new
install, and not if the live Hub'Eau/Open-Meteo APIs happen to be
unreachable from wherever the platform is deployed. A fixed random seed
(`random.Random(20260921)`) makes every run produce byte-identical values,
so `reset()` always returns the demo to the exact same known-good state —
required for reliable, repeatable judging/demo runs.

This intentionally reuses each connector's own station identity (code,
name, coordinates) so the backfilled rows land on the *same* station a live
ingestion run would use — a demo reset never creates a duplicate "fake"
station next to the real one.

Per D006 (locked decision), `is_backfill` is set on these rows purely for
internal bookkeeping (so `reset()` can find and replace them); it is never
surfaced to the frontend as a LIVE/CACHED/REPLAY-style badge.

Run with:
    python -m app.seed.seed_environmental          # seed only if empty
    python -m app.seed.seed_environmental --reset   # wipe + reseed
"""
from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.environmental import DataSource, Measurement, MeasurementVariable, Station, StationKind
from app.services.connectors.hubeau import HubeauHydrometrieConnector
from app.services.connectors.open_meteo import OpenMeteoConnector
from app.services.ingestion_service import get_or_create_data_source

# Session 017 (user request): the dashboard's duration selector offers
# 48h/72h/96h/120h, so the backfill window is now 120h (5 days) — the
# longest of those options — so every one of the 4 buttons shows genuinely
# distinct data instead of 72h/96h/120h all silently repeating the same 48h
# of history. The dashboard's own "limited history" notice
# (CommandCenterView.vue, also added this session) stays in place as a
# safety net for any window still wider than what's actually backfilled.
BACKFILL_HOURS = 120
DEMO_SEED = 20260921  # arbitrary but fixed: today's date at design time


def _generate_hydro_backfill(rng: random.Random, now: datetime) -> list[tuple[MeasurementVariable, float, str, datetime]]:
    """Garonne water height (mm): gentle baseline with a small daily wave and
    light noise — plausible September low-water Toulouse conditions."""
    points = []
    baseline = 410.0
    step = timedelta(minutes=15)
    steps = int(BACKFILL_HOURS * 60 / 15)
    for i in range(steps, 0, -1):
        observed_at = now - step * i
        hours_ago = i * 15 / 60
        wave = 6.0 * math.sin(hours_ago / 12.0 * math.pi)
        noise = rng.uniform(-2.0, 2.0)
        value = round(baseline + wave + noise, 1)
        points.append((MeasurementVariable.WATER_LEVEL_MM, value, "mm", observed_at))
    return points


def _generate_weather_backfill(rng: random.Random, now: datetime) -> list[tuple[MeasurementVariable, float, str, datetime]]:
    """Hourly precipitation/soil moisture/temperature/humidity: a plausible
    late-September Toulouse diurnal cycle with a couple of light rain
    events, deterministic given the fixed seed."""
    points: list[tuple[MeasurementVariable, float, str, datetime]] = []
    step = timedelta(hours=1)
    rain_event_hours = set(rng.sample(range(BACKFILL_HOURS), k=3))
    soil_moisture = 0.26
    for i in range(BACKFILL_HOURS, 0, -1):
        observed_at = (now - step * i).replace(minute=0, second=0, microsecond=0)
        hour_of_day = observed_at.hour

        precipitation = round(rng.uniform(0.4, 3.5), 1) if i in rain_event_hours else 0.0
        soil_moisture = max(0.15, min(0.4, soil_moisture + (0.01 if precipitation > 0 else -0.002)))
        temperature = round(16.0 + 7.0 * math.sin((hour_of_day - 6) / 24.0 * 2 * math.pi) + rng.uniform(-0.6, 0.6), 1)
        humidity = round(60.0 - 15.0 * math.sin((hour_of_day - 6) / 24.0 * 2 * math.pi) + rng.uniform(-4, 4), 1)
        humidity = max(30.0, min(95.0, humidity))
        # P2.1: 4 more free hourly variables, plausible late-September
        # Toulouse conditions, deterministic given the fixed seed.
        wind_speed = round(max(0.0, 12.0 + rng.uniform(-6.0, 8.0)), 1)
        wind_direction = round(rng.uniform(0.0, 360.0), 0)
        surface_pressure = round(996.0 + rng.uniform(-4.0, 4.0), 1)
        uv_index = round(max(0.0, 5.5 * math.sin((hour_of_day - 6) / 24.0 * 2 * math.pi) + rng.uniform(-0.3, 0.3)), 1)

        points.append((MeasurementVariable.PRECIPITATION_MM, precipitation, "mm", observed_at))
        points.append((MeasurementVariable.SOIL_MOISTURE_RATIO, round(soil_moisture, 3), "m3/m3", observed_at))
        points.append((MeasurementVariable.TEMPERATURE_C, temperature, "°C", observed_at))
        points.append((MeasurementVariable.HUMIDITY_PERCENT, humidity, "%", observed_at))
        points.append((MeasurementVariable.WIND_SPEED_KMH, wind_speed, "km/h", observed_at))
        points.append((MeasurementVariable.WIND_DIRECTION_DEG, wind_direction, "°", observed_at))
        points.append((MeasurementVariable.SURFACE_PRESSURE_HPA, surface_pressure, "hPa", observed_at))
        points.append((MeasurementVariable.UV_INDEX, uv_index, "index", observed_at))
    return points


def _get_or_create_station_for(db: Session, source: DataSource, *, external_code, name, kind, city, river_name, lon, lat) -> Station:
    station = db.execute(
        select(Station).where(Station.data_source_id == source.id, Station.external_code == external_code)
    ).scalar_one_or_none()
    if station is None:
        station = Station(
            data_source_id=source.id,
            external_code=external_code,
            name=name,
            kind=kind.value,
            city=city,
            river_name=river_name,
            geom=f"SRID=4326;POINT({lon} {lat})",
        )
        db.add(station)
        db.flush()
    return station


def _seed_source(db: Session, now: datetime) -> None:
    hubeau = HubeauHydrometrieConnector()
    hubeau_source = get_or_create_data_source(db, hubeau)
    hubeau_station = _get_or_create_station_for(
        db,
        hubeau_source,
        external_code=hubeau.station_code,
        name=hubeau.station_name,
        kind=StationKind.RIVER_GAUGE,
        city=hubeau.city,
        river_name=hubeau.river_name,
        lon=hubeau.default_lon,
        lat=hubeau.default_lat,
    )

    open_meteo = OpenMeteoConnector()
    open_meteo_source = get_or_create_data_source(db, open_meteo)
    open_meteo_station = _get_or_create_station_for(
        db,
        open_meteo_source,
        external_code=f"open_meteo_{open_meteo.city.lower()}",
        name=f"Open-Meteo — {open_meteo.city}",
        kind=StationKind.WEATHER_POINT,
        city=open_meteo.city,
        river_name=None,
        lon=open_meteo.lon,
        lat=open_meteo.lat,
    )
    db.flush()

    existing_hydro = db.execute(select(Measurement.id).where(Measurement.station_id == hubeau_station.id).limit(1)).first()
    existing_weather = db.execute(
        select(Measurement.id).where(Measurement.station_id == open_meteo_station.id).limit(1)
    ).first()

    rng = random.Random(DEMO_SEED)
    if existing_hydro is None:
        rows = [
            Measurement(station_id=hubeau_station.id, variable=v.value, value=val, unit=u, observed_at=t, is_backfill=True)
            for v, val, u, t in _generate_hydro_backfill(rng, now)
        ]
        db.bulk_save_objects(rows)
    if existing_weather is None:
        rows = [
            Measurement(station_id=open_meteo_station.id, variable=v.value, value=val, unit=u, observed_at=t, is_backfill=True)
            for v, val, u, t in _generate_weather_backfill(rng, now)
        ]
        db.bulk_save_objects(rows)
    db.commit()


def run() -> None:
    """Seed deterministic backfill only where a station has no data yet — safe to call every startup."""
    db = SessionLocal()
    try:
        _seed_source(db, datetime.now(timezone.utc))
        print("Environmental demo seed: OK (only filled stations with no existing data).", file=sys.stderr)
    finally:
        db.close()


def reset() -> None:
    """Wipe ALL environmental data (stations and measurements, live-ingested and
    backfilled alike) and reseed from scratch — restores the exact known-good
    demo state. Stations are deleted (not just measurements) so this also
    picks up any connector metadata changes (e.g. a corrected coordinate) —
    `Measurement` rows cascade-delete automatically via the FK."""
    db = SessionLocal()
    try:
        db.execute(delete(Station))
        db.commit()
        _seed_source(db, datetime.now(timezone.utc))
        print("Environmental demo reset: OK (stations + measurements rebuilt from scratch).", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
    else:
        run()
