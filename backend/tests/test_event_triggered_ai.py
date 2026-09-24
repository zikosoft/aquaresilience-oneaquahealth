"""Session 017 — event-triggered AI.

Settings > AI Provider's "Event-triggered analysis" toggle has existed
since P3 (stored on AIProviderConfig, shown and saved in the UI) but the
scheduler never read it — flipping it changed nothing (real-machine user
report). `should_run_event_triggered_analysis` is the gate now wired into
the scheduler tick (app.core.scheduler): reuses the same
isolated_db/_FakeAIProvider idiom as test_intelligence.py, and only tests
the gate function directly (not the full scheduler `_tick()`, which also
runs real ingestion connectors — out of scope and would need network).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, event
from sqlalchemy.orm import Session
import pytest

from app.core.database import engine
from app.core.security import encrypt_secret
from app.models.intelligence import SituationBrief
from app.models.settings import AIProviderConfig
from app.services.intelligence_service import get_or_create_ai_config, should_run_event_triggered_analysis


@pytest.fixture()
def isolated_db():
    connection = engine.connect()
    outer_txn = connection.begin()
    session = Session(bind=connection, future=True)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction) -> None:
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    session.execute(delete(SituationBrief))
    session.execute(delete(AIProviderConfig))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


def _configured_config(db, **overrides) -> AIProviderConfig:
    config = get_or_create_ai_config(db)
    defaults = dict(
        provider="openai",
        model="gpt-4o-mini",
        encrypted_api_key=encrypt_secret("fake-key"),
        event_triggered_enabled=True,
        cooldown_seconds=900,
        daily_request_ceiling=6,
        last_analysis_attempt_at=None,
        last_analysis_error=None,
        requests_today=0,
        requests_today_date=None,
    )
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return config


def test_no_open_warning_never_triggers(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db)
    assert should_run_event_triggered_analysis(config, None, now) is False


def test_moderate_severity_does_not_trigger(isolated_db):
    """MODERATE already opens a Warning (OPEN_SEVERITIES in risk_engine.py)
    but is deliberately below the bar for an AI-consuming "event" — only
    HIGH/CRITICAL count, or this would fire on almost every tick."""
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db)
    assert should_run_event_triggered_analysis(config, "MODERATE", now) is False


def test_toggle_disabled_never_triggers_even_at_critical(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db, event_triggered_enabled=False)
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is False


def test_high_or_critical_with_toggle_on_triggers(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db)
    assert should_run_event_triggered_analysis(config, "HIGH", now) is True
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is True


def test_respects_the_same_cooldown_as_manual_refresh(isolated_db):
    """An event trigger must never bypass the budget a human refresh is
    held to — reuses can_run_manual_analysis under the hood."""
    now = datetime.now(timezone.utc)
    config = _configured_config(
        isolated_db, last_analysis_attempt_at=now - timedelta(seconds=30), cooldown_seconds=900
    )
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is False

    config = _configured_config(
        isolated_db, last_analysis_attempt_at=now - timedelta(seconds=1000), cooldown_seconds=900
    )
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is True


def test_respects_the_same_daily_ceiling_as_manual_refresh(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(
        isolated_db, daily_request_ceiling=1, requests_today=1, requests_today_date=now.date()
    )
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is False


def test_not_configured_never_triggers(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db, encrypted_api_key=None)
    assert should_run_event_triggered_analysis(config, "CRITICAL", now) is False
