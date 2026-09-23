"""Ingestion: runs connectors, upserts stations/measurements idempotently,
and tracks per-source health for the freshness/stale/degraded gate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.environmental import DataSource, Measurement, Station
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

logger = logging.getLogger(__name__)


class SourceHealth(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"


# A source that has failed this many consecutive attempts is "degraded"
# regardless of how recent its last success was — repeated failures are a
# real signal even if the last good reading is technically still "fresh" by
# the clock.
DEGRADED_AFTER_CONSECUTIVE_FAILURES = 3


def compute_source_health(source: DataSource, now: datetime | None = None) -> SourceHealth:
    now = now or datetime.now(timezone.utc)
    if source.consecutive_failures >= DEGRADED_AFTER_CONSECUTIVE_FAILURES:
        return SourceHealth.DEGRADED
    if source.last_success_at is None:
        return SourceHealth.DEGRADED
    age_seconds = (now - source.last_success_at).total_seconds()
    if age_seconds > source.stale_after_seconds:
        return SourceHealth.STALE
    return SourceHealth.FRESH


def get_or_create_data_source(db: Session, connector: BaseConnector) -> DataSource:
    source = db.execute(select(DataSource).where(DataSource.code == connector.source_code)).scalar_one_or_none()
    if source is None:
        source = DataSource(
            code=connector.source_code,
            name=connector.source_name,
            provider=connector.provider.value,
            kind=connector.kind.value,
            license=connector.license,
            homepage_url=connector.homepage_url,
            expected_interval_seconds=connector.expected_interval_seconds,
            stale_after_seconds=connector.stale_after_seconds,
        )
        db.add(source)
        db.flush()
    return source


def _get_or_create_station(db: Session, source: DataSource, reading: NormalizedReading) -> Station:
    station = db.execute(
        select(Station).where(
            Station.data_source_id == source.id,
            Station.external_code == reading.station_external_code,
        )
    ).scalar_one_or_none()
    point_wkt = f"SRID=4326;POINT({reading.lon} {reading.lat})"
    if station is None:
        station = Station(
            data_source_id=source.id,
            external_code=reading.station_external_code,
            name=reading.station_name,
            kind=reading.station_kind.value,
            city=reading.city,
            river_name=reading.river_name,
            geom=point_wkt,
        )
        db.add(station)
        db.flush()
    return station


def _upsert_measurements(db: Session, station_id, readings: list[NormalizedReading], is_backfill: bool) -> int:
    """Idempotent bulk insert: ON CONFLICT (station_id, variable, observed_at) DO NOTHING.

    Re-running ingestion for a window that was already ingested is always
    safe and a no-op for the rows that already exist — this is the P1 gate's
    idempotency requirement.
    """
    if not readings:
        return 0
    rows = [
        {
            "station_id": station_id,
            "variable": r.variable.value,
            "value": r.value,
            "unit": r.unit,
            "observed_at": r.observed_at,
            "is_backfill": is_backfill,
        }
        for r in readings
    ]
    stmt = pg_insert(Measurement).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_measurement_station_variable_time")
    # `result.rowcount` is unreliable (-1) for INSERT ... ON CONFLICT via
    # psycopg3 — RETURNING + counting the returned rows gives the exact
    # number of rows actually inserted (conflicting rows return nothing).
    stmt = stmt.returning(Measurement.id)
    result = db.execute(stmt)
    return len(result.fetchall())


def run_connector(db: Session, connector: BaseConnector, is_backfill: bool = False) -> dict:
    """Runs one connector end-to-end: fetch -> upsert stations/measurements -> record health.

    Never raises — a connector failure is expected, routine behavior (a
    flaky upstream API) and must not take down the whole ingestion cycle or
    the request that triggered it. The caller gets back a small summary dict
    instead.
    """
    source = get_or_create_data_source(db, connector)
    now = datetime.now(timezone.utc)
    source.last_attempt_at = now

    try:
        readings = connector.fetch()
    except ConnectorError as exc:
        source.consecutive_failures += 1
        source.last_error_message = str(exc)[:1024]
        db.commit()
        logger.warning("Connector %s failed: %s", connector.source_code, exc)
        return {"source": connector.source_code, "ok": False, "error": str(exc), "inserted": 0}
    except Exception as exc:  # noqa: BLE001 — defensive: a connector must never crash ingestion
        source.consecutive_failures += 1
        source.last_error_message = f"Unexpected error: {exc}"[:1024]
        db.commit()
        logger.exception("Connector %s raised an unexpected error", connector.source_code)
        return {"source": connector.source_code, "ok": False, "error": str(exc), "inserted": 0}

    # Group readings by station so we only look up/create each station once.
    stations_by_code: dict[str, Station] = {}
    inserted_total = 0
    by_station: dict[str, list[NormalizedReading]] = {}
    for reading in readings:
        by_station.setdefault(reading.station_external_code, []).append(reading)

    for external_code, station_readings in by_station.items():
        station = stations_by_code.get(external_code)
        if station is None:
            station = _get_or_create_station(db, source, station_readings[0])
            stations_by_code[external_code] = station
        inserted_total += _upsert_measurements(db, station.id, station_readings, is_backfill)

    source.consecutive_failures = 0
    source.last_error_message = None
    source.last_success_at = now
    db.commit()

    return {"source": connector.source_code, "ok": True, "error": None, "inserted": inserted_total}


def run_all_connectors(db: Session, connectors: list[BaseConnector], is_backfill: bool = False) -> list[dict]:
    return [run_connector(db, connector, is_backfill=is_backfill) for connector in connectors]
