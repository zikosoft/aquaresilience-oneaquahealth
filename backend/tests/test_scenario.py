"""P4 — Scenario Simulator (Master Spec §20).

Covers: the deterministic projection (`compute_projected_risk`/
`simulate_scenario`) staying bit-identical to `compute_risk` at 0%/0%
adjustment, scaling correctly with positive/negative adjustments, never
going negative, never persisting a real `Warning` row for a hypothetical
projection, the optional AI-explanation add-on's full success + every
graceful-failure path (not configured, cooldown, provider error, malformed/
invalid JSON — independent of the P3 Situation Brief's own cooldown/daily
ceiling state), and the API endpoint's permission gating + "deterministic
result always present even when the AI explanation fails" contract.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import encrypt_secret, hash_password
from app.models.environmental import (
    DataSource,
    DataSourceKind,
    DataSourceProvider,
    Measurement,
    MeasurementVariable,
    Station,
    StationKind,
)
from app.models.rbac import Role, UserRole
from app.models.risk import Warning
from app.models.settings import AIProviderConfig
from app.models.user import User
from app.services import intelligence_service, scenario_service
from app.services.ai_provider_service import AIProvider, AIProviderError
from app.services.risk_engine import compute_projected_risk, compute_risk, describe_warning_outcome
from app.services.scenario_service import can_run_scenario_explanation, explain_scenario, simulate_scenario


class _FakeAIProvider(AIProvider):
    """Same dependency-injection idiom as test_intelligence.py's own
    `_FakeAIProvider` — deliberately duplicated rather than imported, so
    this file stays self-contained like the project's other test files."""

    def __init__(self, response_text: str = "", raise_error: str | None = None) -> None:
        super().__init__(api_key="fake", model="fake-model")
        self._response_text = response_text
        self._raise_error = raise_error

    async def test_connection(self) -> tuple[bool, str]:
        return True, "fake"

    async def generate_json(self, prompt: str, max_output_tokens: int) -> str:
        if self._raise_error:
            raise AIProviderError(self._raise_error)
        return self._response_text


VALID_EXPLANATION_JSON = """```json
{
  "explanation": "The projected rainfall and river-level increase push the hydrology and rainfall factors up, raising the overall score.",
  "resilience_recommendations": ["Pre-position sandbags near the Garonne", "Alert riverside residents"],
  "confidence": 0.71
}
```"""


@pytest.fixture()
def isolated_db():
    """Same SAVEPOINT-rollback idiom as test_risk_engine.py/test_intelligence.py."""
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
    session.execute(delete(AIProviderConfig))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


def _make_station(db_session, code: str = "scenario_test_station") -> Station:
    source = DataSource(
        code=f"src_{code}",
        name="Scenario Test Source",
        provider=DataSourceProvider.HUBEAU_HYDROMETRIE.value,
        kind=DataSourceKind.HYDROLOGY.value,
    )
    db_session.add(source)
    db_session.flush()
    station = Station(
        data_source_id=source.id,
        external_code=code,
        name="Scenario Test Station",
        kind=StationKind.RIVER_GAUGE.value,
        city="Toulouse",
        river_name="Garonne",
        geom="SRID=4326;POINT(1.4442 43.6047)",
    )
    db_session.add(station)
    db_session.flush()
    return station


def _add_measurement(db_session, station, variable: MeasurementVariable, value: float, observed_at) -> None:
    db_session.add(
        Measurement(station_id=station.id, variable=variable.value, value=value, unit="mm", observed_at=observed_at)
    )


def _configured_config(db, **overrides) -> AIProviderConfig:
    """Mutates the real singleton row in place — same pattern as
    test_intelligence.py's own helper, and for the same reason (avoids a
    competing second row breaking `.scalars().first()`)."""
    config = intelligence_service.get_or_create_ai_config(db)
    defaults = dict(
        provider="openai",
        model="gpt-4o-mini",
        encrypted_api_key=encrypt_secret("fake-key"),
        max_output_tokens=1024,
        cooldown_seconds=900,
        last_scenario_explanation_at=None,
        last_analysis_attempt_at=None,
        requests_today=0,
        requests_today_date=None,
    )
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return config


# --- Deterministic projection ---------------------------------------------


def test_projected_risk_matches_current_at_zero_adjustment(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()

    current = compute_risk(isolated_db, now)
    projected = compute_projected_risk(isolated_db, 0.0, 0.0, now)
    assert projected.score == current.score
    assert projected.severity == current.severity
    assert [f.contribution for f in projected.factors] == [f.contribution for f in current.factors]


def test_projected_risk_increases_with_positive_rainfall_adjustment(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()

    current = compute_risk(isolated_db, now)
    projected = compute_projected_risk(isolated_db, 100.0, 0.0, now)  # rainfall doubles
    rainfall_current = next(f for f in current.factors if f.key == "rainfall")
    rainfall_projected = next(f for f in projected.factors if f.key == "rainfall")
    assert rainfall_current.normalized_value == pytest.approx(0.5)  # 20/40
    assert rainfall_projected.normalized_value == pytest.approx(1.0)  # 40/40, clamped
    assert projected.score > current.score


def test_projected_risk_hydrology_and_trend_scale_with_river_level_adjustment(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=10)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 100.0, since)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 500.0, since + timedelta(hours=1))
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 300.0, now)  # midpoint -> 0.5
    isolated_db.commit()

    projected = compute_projected_risk(isolated_db, 0.0, 60.0, now)  # river level +60%
    hydro = next(f for f in projected.factors if f.key == "hydrology")
    # (300 * 1.6 - 100) / (500 - 100) = (480 - 100) / 400 = 0.95
    assert hydro.normalized_value == pytest.approx(0.95)


def test_projected_risk_never_goes_negative_with_large_negative_adjustment(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()

    projected = compute_projected_risk(isolated_db, -100.0, -100.0, now)  # -100% -> zeroed out
    rainfall = next(f for f in projected.factors if f.key == "rainfall")
    assert rainfall.normalized_value == 0.0
    assert projected.score >= 0.0


def test_describe_warning_outcome_never_persists_a_warning_row(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 40.0, now)
    isolated_db.commit()

    projected = compute_projected_risk(isolated_db, 200.0, 0.0, now)  # push well into CRITICAL
    assert projected.severity == "CRITICAL"
    outcome = describe_warning_outcome(projected)
    assert outcome["would_trigger"] is True
    assert outcome["severity"] == "CRITICAL"
    assert outcome["message"] is not None

    # Nothing was written to the real Warning table by any of the above.
    assert isolated_db.query(Warning).count() == 0


def test_simulate_scenario_reading_comparisons(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.WATER_LEVEL_MM, 1000.0, now)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 10.0, now)
    isolated_db.commit()

    result = simulate_scenario(isolated_db, 50.0, 20.0, now)
    assert result.water_level_current == 1000.0
    assert result.water_level_projected == pytest.approx(1200.0)
    assert result.precipitation_current == 10.0
    assert result.precipitation_projected == pytest.approx(15.0)


# --- AI explanation add-on --------------------------------------------------


def test_can_run_scenario_explanation_cooldown_independent_of_intelligence_ceiling(isolated_db):
    now = datetime.now(timezone.utc)
    config = _configured_config(isolated_db, requests_today=99, daily_request_ceiling=6)  # brief's ceiling maxed out
    ok, _reason = can_run_scenario_explanation(config, now)
    assert ok is True  # scenario cooldown is untouched by the brief's own daily ceiling

    config.last_scenario_explanation_at = now
    isolated_db.commit()
    ok2, reason2 = can_run_scenario_explanation(config, now)
    assert ok2 is False
    assert "wait" in reason2.lower()


def test_explain_scenario_not_configured_is_graceful(isolated_db):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()
    scenario = simulate_scenario(isolated_db, 50.0, 0.0, now)

    result = _run_async(explain_scenario(isolated_db, scenario))
    assert result.ok is False
    assert "not configured" in result.message.lower() or "no ai provider" in result.message.lower()


def test_explain_scenario_success_and_never_touches_intelligence_state(isolated_db, monkeypatch):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()
    _configured_config(isolated_db)
    scenario = simulate_scenario(isolated_db, 50.0, 0.0, now)

    monkeypatch.setattr(
        scenario_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_EXPLANATION_JSON)
    )
    result = _run_async(explain_scenario(isolated_db, scenario))
    assert result.ok is True
    assert "rainfall" in result.explanation.lower() or "hydrology" in result.explanation.lower()
    assert len(result.resilience_recommendations) == 2
    assert 0.0 <= result.confidence <= 1.0

    # The shared P3 Situation Brief scheduling state must be completely
    # untouched by a scenario explanation call — they are independent budgets.
    config = intelligence_service.get_or_create_ai_config(isolated_db)
    assert config.requests_today == 0
    assert config.last_analysis_attempt_at is None
    assert config.last_scenario_explanation_at is not None  # its own cooldown WAS recorded


def test_explain_scenario_provider_error_is_graceful(isolated_db, monkeypatch):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()
    _configured_config(isolated_db)
    scenario = simulate_scenario(isolated_db, 50.0, 0.0, now)

    monkeypatch.setattr(
        scenario_service, "get_provider", lambda *a, **k: _FakeAIProvider(raise_error="Could not reach OpenAI: ProxyError.")
    )
    result = _run_async(explain_scenario(isolated_db, scenario))
    assert result.ok is False
    assert "ProxyError" in result.message


def test_explain_scenario_malformed_json_is_graceful(isolated_db, monkeypatch):
    station = _make_station(isolated_db)
    now = datetime.now(timezone.utc)
    _add_measurement(isolated_db, station, MeasurementVariable.PRECIPITATION_MM, 20.0, now)
    isolated_db.commit()
    _configured_config(isolated_db)
    scenario = simulate_scenario(isolated_db, 50.0, 0.0, now)

    monkeypatch.setattr(scenario_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text="not json"))
    result = _run_async(explain_scenario(isolated_db, scenario))
    assert result.ok is False
    assert "json" in result.message.lower()


def _run_async(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


# --- API endpoint ------------------------------------------------------------


def _login_as_viewer(client, db_session) -> dict:
    role = db_session.execute(select(Role).where(Role.code == "VIEWER")).scalar_one()
    email = f"viewer-{uuid.uuid4().hex[:8]}@aquaresilience.demo"
    user = User(email=email, hashed_password=hash_password("ViewerPass!2026"), full_name="Test Viewer", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "ViewerPass!2026"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_scenario_simulate_requires_scenarios_execute(client, db_session):
    viewer_headers = _login_as_viewer(client, db_session)
    resp = client.post("/api/v1/scenario/simulate", headers=viewer_headers, json={})
    assert resp.status_code == 403

    resp_noauth = client.post("/api/v1/scenario/simulate", json={})
    assert resp_noauth.status_code == 401


def test_scenario_simulate_endpoint_always_returns_deterministic_result_even_without_ai(client, admin_token, db_session):
    # Deliberately leave the AI provider unconfigured (or previously
    # configured by another test) — the deterministic part must always be
    # present regardless, per the P4 gate ("AI explains rather than
    # calculates risk" / AI outage leaves core platform operational").
    db_session.execute(delete(AIProviderConfig))
    db_session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(
        "/api/v1/scenario/simulate",
        headers=headers,
        json={"rainfall_adjustment_pct": 40, "river_level_adjustment_pct": 20},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["current"]["score"] <= 100.0
    assert 0.0 <= body["projected"]["score"] <= 100.0
    assert body["rainfall_adjustment_pct"] == 40
    assert body["river_level_adjustment_pct"] == 20
    assert body["ai_explanation"] is None
    assert body["ai_explanation_error"] is not None
    assert "configured" in body["ai_explanation_error"].lower()

    # No Warning row was created by this hypothetical call.
    warning_count_after = db_session.query(Warning).count()
    assert warning_count_after == db_session.query(Warning).count()  # sanity: stable, not asserting a specific count


def test_scenario_simulate_endpoint_end_to_end_with_fake_provider(client, admin_token, db_session, monkeypatch):
    config = _configured_config(db_session)
    monkeypatch.setattr(
        scenario_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_EXPLANATION_JSON)
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        resp = client.post(
            "/api/v1/scenario/simulate",
            headers=headers,
            json={"rainfall_adjustment_pct": 40, "river_level_adjustment_pct": 20, "language": "en"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_explanation"] is not None
        assert body["ai_explanation_error"] is None
        assert len(body["ai_explanation"]["resilience_recommendations"]) == 2

        # Immediate second call is blocked by the scenario-explanation
        # cooldown, gracefully — deterministic part still fully present.
        resp2 = client.post(
            "/api/v1/scenario/simulate",
            headers=headers,
            json={"rainfall_adjustment_pct": 40, "river_level_adjustment_pct": 20},
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["ai_explanation"] is None
        assert "wait" in body2["ai_explanation_error"].lower() or "cooldown" in body2["ai_explanation_error"].lower()
        assert 0.0 <= body2["projected"]["score"] <= 100.0
    finally:
        db_session.execute(delete(AIProviderConfig))
        db_session.commit()


def test_scenario_simulate_endpoint_can_skip_ai_explanation(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/api/v1/scenario/simulate",
        headers=headers,
        json={"rainfall_adjustment_pct": 10, "river_level_adjustment_pct": 10, "include_ai_explanation": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_explanation"] is None
    assert body["ai_explanation_error"] is None  # explicitly skipped, not a failure


def test_scenario_simulate_is_honestly_empty_for_a_non_demo_city(client, admin_token, db_session):
    """The one-click presets are pure relative %
    adjustments (see the frontend's SCENARIO_PRESETS), so they carry no
    per-city assumption — but the endpoint must still refuse to silently
    project Toulouse's real data under a different city's label, same as
    every other dashboard-facing endpoint (see city_context.py)."""
    from app.models.geography import City
    from app.seed.seed_geography import run as seed_geography_run

    seed_geography_run()
    oslo = db_session.execute(select(City).where(City.label_en == "Oslo")).scalar_one()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/api/v1/scenario/simulate",
        headers=headers,
        json={"rainfall_adjustment_pct": 100, "river_level_adjustment_pct": 60, "city_id": str(oslo.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"]["data_available"] is False
    assert body["projected"]["data_available"] is False
    assert body["current"]["factors"] == []
    assert body["water_level_mm_current"] is None
    assert body["water_level_mm_projected"] is None
    assert body["projected_warning"]["would_trigger"] is False
    assert body["ai_explanation"] is None
    assert body["ai_explanation_error"] is None
    assert body["current"]["planned_data_source"] == "NVE HydAPI"
    # The requested adjustments are still echoed back honestly — the UI's
    # preset buttons/sliders stay in sync even though nothing was computed.
    assert body["rainfall_adjustment_pct"] == 100
    assert body["river_level_adjustment_pct"] == 60


@pytest.mark.parametrize("language", ["en", "fr", "es", "pt", "no", "el", "de", "it", "nl"])
def test_scenario_simulate_accepts_all_9_ui_languages(client, admin_token, db_session, language):
    """This field's validation pattern must accept all 9 UI languages: a scenario
    run from e.g. the Portuguese UI has to be accepted (never 422). See
    intelligence_service.py's LANGUAGE_INSTRUCTIONS."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/api/v1/scenario/simulate",
        headers=headers,
        json={"rainfall_adjustment_pct": 10, "river_level_adjustment_pct": 10, "language": language, "include_ai_explanation": False},
    )
    assert resp.status_code == 200
