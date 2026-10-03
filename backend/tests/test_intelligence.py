"""P3 — AI Resilience Intelligence.

Covers: environmental snapshot assembly, JSON extraction tolerance,
schema validation of the AI's output, the full generate_situation_brief
orchestration (success + every graceful-failure path — not configured, bad
key, provider error, malformed JSON, schema-invalid JSON), the
scheduling/cooldown/daily-ceiling gates, and the API endpoints' permission
gating and "no unnecessary LLM call" behavior. A `_FakeAIProvider` (same
dependency-injection idiom as `_FakeConnector` in test_environmental.py)
stands in for a real network call throughout — this suite intentionally
never talks to a real AI provider.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import encrypt_secret, hash_password
from app.models.geography import City
from app.models.intelligence import SituationBrief
from app.models.rbac import Role, UserRole
from app.models.settings import AIProviderConfig
from app.models.user import User
from app.services import intelligence_service
from app.services.ai_provider_service import AIProvider, AIProviderError
from app.services.intelligence_service import (
    build_environmental_snapshot,
    can_run_manual_analysis,
    generate_situation_brief,
    pick_next_scheduled_city_id,
    should_run_scheduled_analysis,
)


class _FakeAIProvider(AIProvider):
    """Returns whatever text was handed to it at construction time, or
    raises AIProviderError if `raise_error` is set — never makes a real
    HTTP call."""

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


VALID_BRIEF_JSON = """```json
{
  "situation": "moderate",
  "summary": "Water levels are rising moderately following recent rainfall.",
  "drivers": ["Rising Garonne level", "Recent rainfall"],
  "zones_to_watch": ["Riverside districts"],
  "recommendations": ["Monitor river gauges closely", "Prepare sandbag stock"],
  "confidence": 0.78,
  "limitations": ["Single hydrology station"]
}
```"""


@pytest.fixture()
def isolated_db():
    """Same SAVEPOINT-rollback idiom as test_risk_engine.py's isolated_db —
    needed here because AIProviderConfig is a global singleton row and
    SituationBrief history must not leak between tests or across files."""
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
    """Mutates the singleton row in place (via the same get-or-create the
    real app uses) rather than inserting a competing second row — the app
    itself only ever expects exactly one AIProviderConfig to exist, and
    `.scalars().first()` with two rows present would nondeterministically
    pick whichever the DB happens to return first."""
    config = intelligence_service.get_or_create_ai_config(db)
    defaults = dict(
        provider="openai",
        model="gpt-4o-mini",
        encrypted_api_key=encrypt_secret("fake-key"),
        max_output_tokens=1024,
        scheduled_analysis_interval_minutes=240,
        daily_request_ceiling=6,
        cooldown_seconds=900,
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


def test_build_environmental_snapshot_matches_deterministic_risk(isolated_db):
    now = datetime.now(timezone.utc)
    snapshot, risk = build_environmental_snapshot(isolated_db, now)
    assert snapshot["risk"]["score"] == risk.score
    assert snapshot["risk"]["severity"] == risk.severity
    assert len(snapshot["risk"]["factors"]) == risk.factors_total
    assert "monitored_stations" in snapshot["monitoring"]


def test_extract_json_tolerates_code_fences_and_prose():
    assert intelligence_service._extract_json(VALID_BRIEF_JSON) is not None
    assert intelligence_service._extract_json('Sure, here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}
    assert intelligence_service._extract_json("not json at all") is None
    assert intelligence_service._extract_json("") is None


@pytest.mark.asyncio
async def test_generate_situation_brief_success_persists_and_updates_config(isolated_db, monkeypatch):
    config = _configured_config(isolated_db)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_BRIEF_JSON)
    )

    result = await generate_situation_brief(isolated_db, language="en", triggered_by="manual")

    assert result.ok is True
    assert result.brief is not None
    assert result.brief.summary.startswith("Water levels")
    assert result.brief.confidence == 0.78
    assert result.brief.drivers == ["Rising Garonne level", "Recent rainfall"]
    # situation is forced from the deterministic risk severity, never trusted
    # verbatim from the AI's own output — see intelligence_service comment.
    assert result.brief.situation == intelligence_service._SEVERITY_TO_SITUATION[result.brief.risk_severity_snapshot]

    isolated_db.refresh(config)
    assert config.requests_today == 1
    assert config.requests_today_date == datetime.now(timezone.utc).date()
    assert config.last_analysis_attempt_at is not None
    assert config.last_analysis_error is None

    briefs = isolated_db.query(SituationBrief).all()
    assert len(briefs) == 1


@pytest.mark.asyncio
async def test_generate_situation_brief_not_configured_is_graceful(isolated_db):
    # No AIProviderConfig row created at all -> get_or_create makes an
    # unconfigured default one.
    result = await generate_situation_brief(isolated_db, language="en")
    assert result.ok is False
    assert result.brief is None
    assert "not configured" in result.message.lower() or "No AI provider" in result.message


@pytest.mark.asyncio
async def test_generate_situation_brief_provider_error_is_graceful_and_recorded(isolated_db, monkeypatch):
    config = _configured_config(isolated_db)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(raise_error="simulated 401")
    )

    result = await generate_situation_brief(isolated_db, language="en")

    assert result.ok is False
    assert result.brief is None
    isolated_db.refresh(config)
    assert config.last_analysis_error == "simulated 401"
    assert config.requests_today == 1  # a failed attempt still counts against the daily ceiling
    assert isolated_db.query(SituationBrief).count() == 0


@pytest.mark.asyncio
async def test_generate_situation_brief_malformed_json_is_graceful(isolated_db, monkeypatch):
    config = _configured_config(isolated_db)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text="not json at all")
    )

    result = await generate_situation_brief(isolated_db, language="en")

    assert result.ok is False
    isolated_db.refresh(config)
    assert "not valid JSON" in config.last_analysis_error
    assert isolated_db.query(SituationBrief).count() == 0


@pytest.mark.asyncio
async def test_generate_situation_brief_schema_invalid_json_is_graceful(isolated_db, monkeypatch):
    config = _configured_config(isolated_db)
    # confidence out of the 0..1 range -> fails _RawBriefPayload validation.
    bad_json = '{"situation": "moderate", "summary": "x", "drivers": [], "zones_to_watch": [], "recommendations": [], "confidence": 5.0, "limitations": []}'
    monkeypatch.setattr(intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=bad_json))

    result = await generate_situation_brief(isolated_db, language="en")

    assert result.ok is False
    isolated_db.refresh(config)
    assert "schema validation" in config.last_analysis_error
    assert isolated_db.query(SituationBrief).count() == 0


@pytest.mark.asyncio
async def test_generate_situation_brief_defaults_to_primary_city_when_omitted(isolated_db, monkeypatch):
    """Session 022 (user request): omitting city_id (background/legacy
    callers) must keep the original default — the primary city (Toulouse),
    never an unscoped/ambiguous row."""
    _configured_config(isolated_db)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_BRIEF_JSON)
    )

    result = await generate_situation_brief(isolated_db, language="en", triggered_by="manual")

    assert result.ok is True
    toulouse_id = isolated_db.execute(select(City.id).where(City.label_en == "Toulouse")).scalar_one()
    assert result.brief.city_id == toulouse_id


@pytest.mark.asyncio
async def test_generate_situation_brief_respects_explicit_city_id_and_names_it_in_the_prompt(isolated_db, monkeypatch):
    """Session 022 (user request): the brief must follow whichever city is
    passed in, not always Toulouse — and the prompt itself must name that
    city rather than hardcoding 'Toulouse Métropole', or an Oslo brief would
    misleadingly claim to describe Toulouse."""
    _configured_config(isolated_db)
    oslo_id = isolated_db.execute(select(City.id).where(City.label_en == "Oslo")).scalar_one()

    captured_prompts: list[str] = []

    class _CapturingFakeProvider(_FakeAIProvider):
        async def generate_json(self, prompt: str, max_output_tokens: int) -> str:
            captured_prompts.append(prompt)
            return await super().generate_json(prompt, max_output_tokens)

    monkeypatch.setattr(
        intelligence_service,
        "get_provider",
        lambda *a, **k: _CapturingFakeProvider(response_text=VALID_BRIEF_JSON),
    )

    result = await generate_situation_brief(isolated_db, language="en", triggered_by="manual", city_id=oslo_id)

    assert result.ok is True
    assert result.brief.city_id == oslo_id
    assert len(captured_prompts) == 1
    assert "Oslo" in captured_prompts[0]
    assert "Toulouse" not in captured_prompts[0]


def test_pick_next_scheduled_city_id_rotates_across_live_cities(isolated_db):
    """Session 022 (user request): the scheduled slot should go to whichever
    live city's own brief is most overdue (or has none yet), not always
    Toulouse — while never touching a non-live city (nothing real to
    analyze there yet)."""
    toulouse_id = isolated_db.execute(select(City.id).where(City.label_en == "Toulouse")).scalar_one()
    oslo = isolated_db.execute(select(City).where(City.label_en == "Oslo")).scalar_one()

    # Only Toulouse is live by default (test_geography.py asserts this same
    # baseline) -> it's the only candidate.
    assert pick_next_scheduled_city_id(isolated_db) == toulouse_id

    # Flip Oslo live too (same direct-mutation pattern already used by
    # test_environmental.py's has_live_data test). Give Toulouse a brief so
    # Oslo (never analyzed) is unambiguously the more-overdue pick.
    oslo.has_live_data = True
    isolated_db.add(
        SituationBrief(
            generated_at=datetime.now(timezone.utc),
            city_id=toulouse_id,
            language="en",
            triggered_by="scheduled",
            situation="low",
            summary="x",
            drivers=[],
            zones_to_watch=[],
            recommendations=[],
            confidence=0.5,
            limitations=[],
            risk_score_snapshot=0.0,
            risk_severity_snapshot="LOW",
            provider="openai",
            model="gpt-4o-mini",
        )
    )
    isolated_db.commit()

    assert pick_next_scheduled_city_id(isolated_db) == oslo.id


def test_should_run_scheduled_analysis_gates(isolated_db):
    now = datetime.now(timezone.utc)

    unconfigured = AIProviderConfig()
    assert should_run_scheduled_analysis(unconfigured, now) is False

    never_run = _configured_config(isolated_db)
    assert should_run_scheduled_analysis(never_run, now) is True

    just_ran = _configured_config(
        isolated_db, last_analysis_attempt_at=now, scheduled_analysis_interval_minutes=240
    )
    assert should_run_scheduled_analysis(just_ran, now) is False

    interval_elapsed = _configured_config(
        isolated_db,
        last_analysis_attempt_at=now - timedelta(minutes=241),
        scheduled_analysis_interval_minutes=240,
    )
    assert should_run_scheduled_analysis(interval_elapsed, now) is True

    ceiling_reached = _configured_config(
        isolated_db,
        last_analysis_attempt_at=now - timedelta(hours=5),
        daily_request_ceiling=3,
        requests_today=3,
        requests_today_date=now.date(),
    )
    assert should_run_scheduled_analysis(ceiling_reached, now) is False

    # A new UTC day resets the effective count even if the stored counter
    # wasn't physically zeroed yet (that happens lazily on the next write).
    stale_counter_new_day = _configured_config(
        isolated_db,
        last_analysis_attempt_at=now - timedelta(hours=5),
        daily_request_ceiling=3,
        requests_today=3,
        requests_today_date=(now - timedelta(days=1)).date(),
    )
    assert should_run_scheduled_analysis(stale_counter_new_day, now) is True


def test_can_run_manual_analysis_cooldown_and_ceiling(isolated_db):
    now = datetime.now(timezone.utc)

    unconfigured = AIProviderConfig()
    ok, reason = can_run_manual_analysis(unconfigured, now)
    assert ok is False and "configured" in reason.lower()

    fresh = _configured_config(isolated_db, cooldown_seconds=900)
    ok, _ = can_run_manual_analysis(fresh, now)
    assert ok is True

    cooling_down = _configured_config(
        isolated_db, last_analysis_attempt_at=now - timedelta(seconds=30), cooldown_seconds=900
    )
    ok, reason = can_run_manual_analysis(cooling_down, now)
    assert ok is False and "cooldown" in reason.lower()

    ceiling_reached = _configured_config(
        isolated_db,
        daily_request_ceiling=1,
        requests_today=1,
        requests_today_date=now.date(),
    )
    ok, reason = can_run_manual_analysis(ceiling_reached, now)
    assert ok is False and "limit" in reason.lower()


def test_intelligence_endpoints_permission_gated_and_no_llm_call_on_get(client, admin_token, monkeypatch):
    calls = []
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: calls.append(1) or _FakeAIProvider(response_text=VALID_BRIEF_JSON)
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    # GET endpoints must never call the AI provider (P3 gate: no unnecessary
    # LLM call on dashboard load).
    resp = client.get("/api/v1/intelligence/brief", headers=headers)
    assert resp.status_code == 200
    resp = client.get("/api/v1/intelligence/status", headers=headers)
    assert resp.status_code == 200
    assert calls == []

    # No auth at all -> 401, not a silent pass-through.
    resp = client.get("/api/v1/intelligence/brief")
    assert resp.status_code == 401


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


def test_viewer_can_view_but_not_trigger_analysis(client, db_session):
    """VIEWER_GRANTS_PERMISSIONS (seed_data.py) is VIEW-only for
    AI_INTELLIGENCE — only OPERATOR/ADMINISTRATOR get EXECUTE."""
    viewer_headers = _login_as_viewer(client, db_session)

    assert client.get("/api/v1/intelligence/brief", headers=viewer_headers).status_code == 200
    assert client.get("/api/v1/intelligence/status", headers=viewer_headers).status_code == 200
    resp = client.post("/api/v1/intelligence/analyze", headers=viewer_headers, json={})
    assert resp.status_code == 403


@pytest.mark.parametrize("language", ["en", "fr", "es", "pt", "no", "el", "de", "it", "nl"])
def test_analyze_endpoint_accepts_all_9_ui_languages(client, admin_token, db_session, language):
    """Session 019: found while wiring WOW #2 (Scenario Simulator) —
    session 018 added 6 more UI languages but this endpoint's `language`
    field validation was never updated, so a manual analysis request from
    one of those 6 UI languages was rejected outright (422) instead of
    degrading gracefully. Not configuring an AI provider here on purpose:
    the point is that the request is *accepted* (never 422), regardless of
    whether the deterministic ok=False "not configured" path follows."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/v1/intelligence/analyze", headers=headers, json={"language": language})
    assert resp.status_code == 200


def test_analyze_endpoint_end_to_end_with_fake_provider(client, admin_token, db_session, monkeypatch):
    # These two API-level tests go through `client`'s own DB session (a
    # separate connection from `isolated_db`'s SAVEPOINT above, so it can't
    # be reused for HTTP-driven tests — real commits are the only way the
    # app's own request handling sees this data). Cleaned up explicitly at
    # the end so the shared AIProviderConfig singleton doesn't leak a
    # "configured" state into other test files that run after this one
    # (alphabetically: test_settings_secret.py).
    config = _configured_config(db_session)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_BRIEF_JSON)
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        resp = client.post("/api/v1/intelligence/analyze", headers=headers, json={"language": "fr"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["brief"]["language"] == "fr"
        assert body["brief"]["summary"].startswith("Water levels")

        # A second immediate call is blocked by the cooldown, gracefully (still 200, ok=False).
        resp2 = client.post("/api/v1/intelligence/analyze", headers=headers, json={})
        assert resp2.status_code == 200
        assert resp2.json()["ok"] is False
        assert "cooldown" in resp2.json()["message"].lower() or "wait" in resp2.json()["message"].lower()

        # The now-current brief is reflected on GET /brief.
        latest = client.get("/api/v1/intelligence/brief", headers=headers)
        assert latest.json()["language"] == "fr"
    finally:
        db_session.execute(delete(SituationBrief))
        db_session.execute(delete(AIProviderConfig))
        db_session.commit()


def test_brief_and_analyze_endpoints_are_scoped_per_city(client, admin_token, db_session, monkeypatch):
    """Session 022 (user request): both endpoints must follow an explicit
    city_id end-to-end — triggering an analysis for Oslo must not overwrite
    or shadow Toulouse's own latest brief, and GET /brief?city_id=<oslo>
    must return Oslo's, not Toulouse's."""
    _configured_config(db_session)
    monkeypatch.setattr(
        intelligence_service, "get_provider", lambda *a, **k: _FakeAIProvider(response_text=VALID_BRIEF_JSON)
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    oslo_id = str(db_session.execute(select(City.id).where(City.label_en == "Oslo")).scalar_one())

    try:
        resp = client.post("/api/v1/intelligence/analyze", headers=headers, json={"language": "en"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        toulouse_brief_id = resp.json()["brief"]["id"]

        # Clear the cooldown directly so Oslo's own manual trigger (a
        # distinct city, but the same shared daily budget/cooldown) isn't
        # blocked by the Toulouse call just above.
        config_row = db_session.execute(select(AIProviderConfig)).scalar_one()
        config_row.last_analysis_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
        db_session.commit()

        resp2 = client.post(
            "/api/v1/intelligence/analyze", headers=headers, json={"language": "en", "city_id": oslo_id}
        )
        assert resp2.status_code == 200
        assert resp2.json()["ok"] is True
        assert resp2.json()["brief"]["city_id"] == oslo_id

        # Omitting city_id still defaults to Toulouse's own latest brief,
        # unaffected by the Oslo trigger that happened after it.
        toulouse_latest = client.get("/api/v1/intelligence/brief", headers=headers)
        assert toulouse_latest.json()["id"] == toulouse_brief_id

        oslo_latest = client.get("/api/v1/intelligence/brief", headers=headers, params={"city_id": oslo_id})
        assert oslo_latest.json()["city_id"] == oslo_id
        assert oslo_latest.json()["id"] != toulouse_brief_id
    finally:
        db_session.execute(delete(SituationBrief))
        db_session.execute(delete(AIProviderConfig))
        db_session.commit()
