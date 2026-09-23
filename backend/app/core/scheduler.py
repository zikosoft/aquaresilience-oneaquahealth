"""Background ingestion scheduler.

A single APScheduler `BackgroundScheduler` job ticks every
`settings.ingestion_tick_seconds`. On each tick it checks every registered
connector and only actually calls it once that connector's own
`expected_interval_seconds` has elapsed since its last attempt — this lets
one shared job cadence serve sources with very different natural update
rates (Hub'Eau ~5 min, Open-Meteo ~hourly) without per-source cron entries.

Disabled automatically under pytest (`PYTEST_CURRENT_TEST` is set by
pytest itself) and via `ENABLE_INGESTION_SCHEDULER=false`, so tests and
local debugging never make unexpected real network calls in the background.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.connectors import get_connectors
from app.services.ingestion_service import get_or_create_data_source, run_connector
from app.services.risk_engine import compute_risk, evaluate_and_persist_warnings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _tick() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for connector in get_connectors():
            source = get_or_create_data_source(db, connector)
            db.commit()
            last_attempt = source.last_attempt_at
            due = last_attempt is None or (now - last_attempt).total_seconds() >= connector.expected_interval_seconds
            if due:
                run_connector(db, connector)

        # P2: re-evaluate the deterministic risk score and warning lifecycle
        # on every tick too, so warnings escalate/auto-resolve on their own
        # even if nobody has the Command Center open (GET /risk/current does
        # the same idempotent evaluation on demand — see app.api.v1.risk).
        risk_result = compute_risk(db, now)
        evaluate_and_persist_warnings(db, risk_result)
    except Exception:  # noqa: BLE001 — a scheduler tick must never crash the process
        logger.exception("Ingestion scheduler tick failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.enable_ingestion_scheduler or "PYTEST_CURRENT_TEST" in os.environ:
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _tick,
        "interval",
        seconds=settings.ingestion_tick_seconds,
        next_run_time=datetime.now(timezone.utc),  # run once immediately on startup
        id="environmental_ingestion_tick",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Ingestion scheduler started (tick every %ss)", settings.ingestion_tick_seconds)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
