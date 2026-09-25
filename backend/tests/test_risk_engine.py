"""P2 — deterministic risk engine + early warning lifecycle.

Covers: pure-function determinism (same data -> same score, twice in a
row), graceful handling of insufficient per-factor data (weight
renormalization over the factors that ARE available), severity bucketing
against the configured thresholds, warning creation on crossing into
MODERATE+, in-place update on repeated evaluation (no duplicate warnings),
auto-resolve when the score drops back to LOW, the acknowledge/resolve API
actions and their RBAC gating, and the read endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, event
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.environmental import (
    DataSource,
    DataSourceKind,
    DataSourceProvider,
    Measurement,
    MeasurementVariable,
    Station,
    StationKind,
)
from app.models.risk import Warning, WarningStatus
from app.services.risk_engine import compute_risk, compute_risk_trajectory, evaluate_and_persist_warnings


@pytest.fixture()
def isolated_db():
    """A DB session wrapping a real transaction that is ALWAYS rolled back
    at the end of the test, via the standard SQLAlchemy nested-SAVEPOINT
    pattern — needed here specifically because the risk engine's queries
    are deliberately global (this is a single-city, single-hydrology-station
    deployment, so "the latest water level" etc. is meant to mean *the*
    reading, not one scoped to a station id). The shared session-scoped
    `db_session` fixture from conftest.py seeds real P1 demo backfill data
    once for the whole test run, which would otherwise leak into and
    corrupt these tests' exact-value assertions (and vice versa: without
    rollback, rows inserted here would leak into every test that runs
    after this one, including other test files sharing the same DB).

    Rolling back this test's OWN writes at teardown isn't enough by itself
    though: a fresh transaction still sees whatever was already committed
    before it began — including that real seeded backfill. So this fixture
    also deletes all existing Measurement/Warning rows right after opening
    its transaction, giving every test a clean slate. That delete is itself
    scoped to this same rolled-back transaction (MVCC read-your-own-writes:
    only this connection sees it gone), so the real seeded data reappears
    completely unharmed for the next test/fixture instance once this one
    tears down."""
    connection = engine.connect()
    outer_txn = connection.begin()
    session = Session(bind=connection, future=True)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction) -> None:
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    session.execute(delete(Warning))
    session.execute(delete(Measurement))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


def _make_station(db_session, code: str = "risk_test_station") -> Station:
    source = DataSource(
        code=f"src_{code}",
        name="Risk Test Source",
        provider=DataSourceProvider.HUBEAU_HYDROMETRIE.value,
        kind=DataSourceKind.HYDROLOGY.value,
    )
    db_session.add(source)
    db_session.flush()
    station = Station(
        data_source_id=source.id,
        external_code=code,
        name="Risk Test Station",
        kind=StationKind.RIVER_GAUGE.value,
        city="Toulouse",
        river_name="Garonne",
        geom="SRID=4326;POINT(1.4442 43.6047)",
    )
    db_session.add(station)
    db_session.flush()
    return station


def _add_measurement(db_session, station: Station, variable: MeasurementVariable, value: float, observed_at) -> None:
    db_session.add(
        Measurement(
            station_id=station.id,
            variable=variable.value,
            value=value,
            unit="mm",
            observed_at=observed_at,
        )
    )


def test_compute_risk_with_no_data_is_zero_and_low(isolated_db):
    result = compute_risk(isolated_db)
    assert result.score == 0.0
    assert result.severity == "LOW"
    assert result.factors_available == 0
    assert result.factors_total == 4
    assert all(not f.available for f in result.factors)


def test_compute_risk_is_deterministic_for_unchanged_data(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.SOIL_MOISTURE_RATIO, 0.4, now)
    isolated_db.commit()

    result1 = compute_risk(isolated_db, now)
    result2 = compute_risk(isolated_db, now)
    assert result1.score == result2.score
    assert result1.severity == result2.severity
    assert [f.contribution for f in result1.factors] == [f.contribution for f in result2.factors]


def test_compute_risk_renormalizes_weights_over_available_factors_only(isolated_db):
    # Only the environmental factor (soil moisture, weight 0.2 by default)
    # has data. With renormalization, that single factor should carry the
    # FULL 100% of the score rather than being capped at 20%.
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.SOIL_MOISTURE_RATIO, 0.5, now)
    isolated_db.commit()

    result = compute_risk(isolated_db, now)
    assert result.factors_available == 1
    env_factor = next(f for f in result.factors if f.key == "environmental")
    assert env_factor.available is True
    assert env_factor.normalized_value == 0.5
    # Renormalized weight = 1.0 (only available factor) -> contribution = 0.5 * 100 = 50
    assert env_factor.contribution == 50.0
    assert result.score == 50.0


def test_compute_risk_hydrology_factor_uses_relative_historical_range(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=10)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 100.0, since)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 500.0, since + timedelta(hours=1))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 300.0, now)  # midpoint -> 0.5
    isolated_db.commit()

    result = compute_risk(isolated_db, now)
    hydro_factor = next(f for f in result.factors if f.key == "hydrology")
    assert hydro_factor.available is True
    assert hydro_factor.normalized_value == 0.5


def test_compute_risk_hydrology_factor_unavailable_with_flat_range(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    # A single distinct value -> degenerate (flat) range -> not enough signal.
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 200.0, now - timedelta(days=1))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 200.0, now)
    isolated_db.commit()

    result = compute_risk(isolated_db, now)
    hydro_factor = next(f for f in result.factors if f.key == "hydrology")
    assert hydro_factor.available is False


def test_compute_risk_trend_factor_only_counts_rising_levels(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    # Falling level over the trailing window -> trend factor clamps to 0, not negative.
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 500.0, now - timedelta(hours=5))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 400.0, now)
    isolated_db.commit()

    result = compute_risk(isolated_db, now)
    trend_factor = next(f for f in result.factors if f.key == "trend")
    assert trend_factor.available is True
    assert trend_factor.normalized_value == 0.0


def test_risk_trajectory_with_no_data_is_insufficient_and_flat(isolated_db):
    trajectory = compute_risk_trajectory(isolated_db)
    assert trajectory.basis == "insufficient_data"
    assert trajectory.trend_rate_mm_per_hour is None
    assert [p.hours_ahead for p in trajectory.points] == [1, 3, 6, 12]
    assert all(p.score == trajectory.current.score == 0.0 for p in trajectory.points)
    assert all(p.projected_water_level_mm is None for p in trajectory.points)


def test_risk_trajectory_is_flat_for_a_falling_trend(isolated_db):
    # Same falling-level fixture as the trend-factor test above: the honest
    # trajectory for a falling/flat trend is flat, never a fabricated rise.
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 500.0, now - timedelta(hours=5))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 400.0, now)
    isolated_db.commit()

    trajectory = compute_risk_trajectory(isolated_db, now)
    assert trajectory.basis == "flat_or_falling"
    assert trajectory.trend_rate_mm_per_hour == -20.0
    assert all(p.score == trajectory.current.score for p in trajectory.points)


def test_risk_trajectory_extrapolates_a_rising_trend_forward(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    # Rising 60mm/h over the trailing window (100 -> 400 over 5h).
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 100.0, now - timedelta(hours=5))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 400.0, now)
    # A wide historical range so the hydrology factor is available and
    # actually moves as the projected level rises further into it.
    since = now - timedelta(days=10)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 0.0, since)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 2000.0, since + timedelta(hours=1))
    isolated_db.commit()

    trajectory = compute_risk_trajectory(isolated_db, now)
    assert trajectory.basis == "rising_trend"
    assert trajectory.trend_rate_mm_per_hour == 60.0
    assert trajectory.current.score == compute_risk(isolated_db, now).score

    levels = [p.projected_water_level_mm for p in trajectory.points]
    assert levels == [460.0, 580.0, 760.0, 1120.0]  # 400 + 60*hours_ahead
    scores = [p.score for p in trajectory.points]
    # Strictly non-decreasing: a longer horizon never projects a lower score
    # than a shorter one when the trend keeps rising.
    assert scores == sorted(scores)
    assert scores[-1] > trajectory.current.score

    # The trend factor itself must be held fixed across every horizon (see
    # compute_risk_trajectory's docstring, point 3) — recomputed per-point
    # movement should come from hydrology only.
    trend_factor_now = next(f for f in trajectory.current.factors if f.key == "trend")
    assert trend_factor_now.available is True


def test_severity_bucketing_matches_configured_thresholds(isolated_db):
    # Defaults: low=25, moderate=50, high=75.
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    # Rainfall alone (renormalized to 100% weight) at exactly the 40mm
    # reference -> normalized 1.0 -> score 100 -> CRITICAL.
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 40.0, now)
    isolated_db.commit()

    result = compute_risk(isolated_db, now)
    assert result.score == 100.0
    assert result.severity == "CRITICAL"


def test_warning_lifecycle_create_update_and_auto_resolve(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)

    # 1. High rainfall -> MODERATE+ severity -> a new ACTIVE warning is created.
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 40.0, now)
    isolated_db.commit()
    result = compute_risk(isolated_db, now)
    warning = evaluate_and_persist_warnings(isolated_db, result)
    assert warning is not None
    assert warning.status == WarningStatus.ACTIVE.value
    warning_id = warning.id

    all_warnings = isolated_db.query(Warning).all()
    assert len(all_warnings) == 1

    # 2. Re-evaluating with the same conditions must update the SAME warning,
    #    never create a duplicate.
    result2 = compute_risk(isolated_db, now)
    warning2 = evaluate_and_persist_warnings(isolated_db, result2)
    assert warning2.id == warning_id
    assert isolated_db.query(Warning).count() == 1

    # 3. Conditions clear (no more rainfall data in the 24h window) -> severity
    #    drops to LOW -> the open warning is auto-resolved.
    later = now + timedelta(hours=25)
    result3 = compute_risk(isolated_db, later)
    assert result3.severity == "LOW"
    open_warning = evaluate_and_persist_warnings(isolated_db, result3)
    assert open_warning is None

    isolated_db.refresh(warning)
    assert warning.status == WarningStatus.RESOLVED.value
    assert warning.resolved_at is not None


def test_risk_current_endpoint_requires_dashboard_view(client, admin_token):
    resp = client.get("/api/v1/risk/current")
    assert resp.status_code == 401

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/risk/current", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["score"] <= 100.0
    assert body["severity"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert len(body["factors"]) == 4
    assert body["factors_total"] == 4
    assert body["data_available"] is True


def test_risk_current_is_honestly_empty_for_a_non_demo_city(client, admin_token, db_session):
    """Session 018: ?city_id= for a consortium city with no live connector
    (e.g. Oslo) must not silently return Toulouse's numbers under a
    different label — see app/services/city_context.py."""
    from sqlalchemy import select

    from app.models.geography import City
    from app.seed.seed_geography import run as seed_geography_run

    seed_geography_run()
    oslo = db_session.execute(select(City).where(City.label_en == "Oslo")).scalar_one()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/v1/risk/current?city_id={oslo.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_available"] is False
    assert body["score"] == 0.0
    assert body["factors"] == []
    assert body["planned_data_source"] == "NVE HydAPI"


def test_risk_trajectory_endpoint_requires_dashboard_view(client, admin_token):
    resp = client.get("/api/v1/risk/trajectory")
    assert resp.status_code == 401

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/risk/trajectory", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["current_score"] <= 100.0
    assert body["current_severity"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert len(body["points"]) == 4
    assert [p["hours_ahead"] for p in body["points"]] == [1, 3, 6, 12]
    assert body["basis"] in ("rising_trend", "flat_or_falling", "insufficient_data")
    assert body["data_available"] is True


def test_risk_trajectory_is_honestly_empty_for_a_non_demo_city(client, admin_token, db_session):
    from sqlalchemy import select

    from app.models.geography import City
    from app.seed.seed_geography import run as seed_geography_run

    seed_geography_run()
    oslo = db_session.execute(select(City).where(City.label_en == "Oslo")).scalar_one()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/v1/risk/trajectory?city_id={oslo.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_available"] is False
    assert body["points"] == []
    assert body["planned_data_source"] == "NVE HydAPI"


def test_warnings_endpoints_and_actions(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # No auth -> 401.
    assert client.get("/api/v1/risk/warnings").status_code == 401

    # Force a warning into existence directly, deterministically, so this
    # test doesn't depend on the shared seeded environmental data crossing a
    # threshold.
    now = datetime.now(timezone.utc)
    warning = Warning(
        severity="HIGH",
        status=WarningStatus.ACTIVE.value,
        risk_score=80.0,
        factors={},
        message="Test warning",
        triggered_at=now,
    )
    db_session.add(warning)
    db_session.commit()
    db_session.refresh(warning)

    resp = client.get("/api/v1/risk/warnings", headers=headers)
    assert resp.status_code == 200
    assert any(w["id"] == str(warning.id) for w in resp.json())

    # Acknowledge.
    resp = client.post(f"/api/v1/risk/warnings/{warning.id}/acknowledge", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACKNOWLEDGED"
    assert body["acknowledged_at"] is not None
    assert body["acknowledged_by"] == "Demo Administrator"

    # Acknowledging again (no longer ACTIVE) -> conflict.
    resp = client.post(f"/api/v1/risk/warnings/{warning.id}/acknowledge", headers=headers)
    assert resp.status_code == 409

    # Resolve.
    resp = client.post(f"/api/v1/risk/warnings/{warning.id}/resolve", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_at"] is not None

    # Resolving an already-resolved warning -> conflict.
    resp = client.post(f"/api/v1/risk/warnings/{warning.id}/resolve", headers=headers)
    assert resp.status_code == 409

    # Unknown warning id -> 404.
    resp = client.post(
        "/api/v1/risk/warnings/00000000-0000-0000-0000-000000000000/acknowledge", headers=headers
    )
    assert resp.status_code == 404
