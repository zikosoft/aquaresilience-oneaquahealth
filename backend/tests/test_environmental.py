"""P1 — environmental data: sources, stations, timeseries, summary, and the
ingestion pipeline's idempotency/health-computation guarantees."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.environmental import DataSource, DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading
from app.services.ingestion_service import SourceHealth, compute_source_health, get_or_create_data_source, run_connector


class _FakeConnector(BaseConnector):
    source_code = "test_fake_source"
    source_name = "Test Fake Source"
    provider = DataSourceProvider.HUBEAU_HYDROMETRIE
    kind = DataSourceKind.HYDROLOGY
    license = "test"
    homepage_url = "http://example.invalid"
    expected_interval_seconds = 300
    stale_after_seconds = 3600

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        # Frozen once at construction, not recomputed per fetch(): the
        # idempotency test below calls fetch() twice (once per run_connector
        # call) and asserts the second run inserts 0 rows. Recomputing
        # datetime.now() on each call made those two readings' timestamps
        # differ whenever the two calls landed in different wall-clock
        # seconds, so the "same window re-ingested" premise silently broke
        # depending on execution speed (flaky, not a real ingestion bug).
        self._now = datetime.now(timezone.utc).replace(microsecond=0)

    def fetch(self) -> list[NormalizedReading]:
        if self.fail:
            raise ConnectorError("simulated failure")
        now = self._now
        return [
            NormalizedReading(
                "FAKE1", "Fake Station", StationKind.RIVER_GAUGE, "Toulouse", "Garonne", 1.44, 43.60,
                MeasurementVariable.WATER_LEVEL_MM, 420.0, "mm", now,
            ),
            NormalizedReading(
                "FAKE1", "Fake Station", StationKind.RIVER_GAUGE, "Toulouse", "Garonne", 1.44, 43.60,
                MeasurementVariable.WATER_LEVEL_MM, 418.0, "mm", now - timedelta(minutes=5),
            ),
        ]


def test_ingestion_is_idempotent_on_repeated_runs(db_session):
    connector = _FakeConnector()
    result1 = run_connector(db_session, connector)
    assert result1["ok"] is True
    assert result1["inserted"] == 2

    result2 = run_connector(db_session, connector)
    assert result2["ok"] is True
    assert result2["inserted"] == 0  # same window re-ingested: no duplicates


def test_ingestion_failure_is_recorded_without_crashing(db_session):
    connector = _FakeConnector(fail=True)
    result = run_connector(db_session, connector)
    assert result["ok"] is False
    assert "simulated failure" in result["error"]

    source = db_session.query(DataSource).filter_by(code="test_fake_source").one()
    assert source.consecutive_failures == 1
    assert source.last_error_message is not None


def test_source_health_degraded_after_repeated_failures(db_session):
    connector = _FakeConnector(fail=True)
    for _ in range(3):
        run_connector(db_session, connector)
    source = db_session.query(DataSource).filter_by(code="test_fake_source").one()
    assert compute_source_health(source) == SourceHealth.DEGRADED


def test_source_health_stale_after_expected_window(db_session):
    connector = _FakeConnector()
    run_connector(db_session, connector)
    source = db_session.query(DataSource).filter_by(code="test_fake_source").one()
    assert compute_source_health(source) == SourceHealth.FRESH

    # Simulate a source that succeeded a long time ago and hasn't since.
    source.last_success_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()
    assert compute_source_health(source) == SourceHealth.STALE


def test_sources_endpoint_lists_seeded_sources(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/environmental/sources", headers=headers)
    assert resp.status_code == 200
    codes = {s["code"] for s in resp.json()}
    assert "hubeau_hydrometrie_toulouse_garonne" in codes
    assert "open_meteo_toulouse" in codes
    for source in resp.json():
        assert source["health"] in ("fresh", "stale", "degraded")


def test_stations_endpoint_returns_seeded_stations_with_coordinates(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/environmental/stations", headers=headers)
    assert resp.status_code == 200
    stations = resp.json()
    assert len(stations) >= 2
    for station in stations:
        assert -180 <= station["lon"] <= 180
        assert -90 <= station["lat"] <= 90
        assert isinstance(station["latest"], list)


def test_station_timeseries_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    stations = client.get("/api/v1/environmental/stations", headers=headers).json()
    hydro_station = next(s for s in stations if s["kind"] == "river_gauge")
    resp = client.get(
        f"/api/v1/environmental/stations/{hydro_station['id']}/timeseries?hours=48",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["station_id"] == hydro_station["id"]
    assert len(body["series"]) >= 1
    assert body["series"][0]["points"]


def test_station_timeseries_404_for_unknown_station(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(
        "/api/v1/environmental/stations/00000000-0000-0000-0000-000000000000/timeseries",
        headers=headers,
    )
    assert resp.status_code == 404


def test_environmental_summary_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/environmental/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitored_stations"] >= 2
    assert body["water_level"] is not None
    assert body["temperature"] is not None
    assert body["humidity"] is not None
    assert body["trend_window_hours"] == 48  # default
    # P1.1 hotfix: temperature/humidity trends, added to fill the Command
    # Center KPI row from 2 to 4 sparklines from already-ingested data (no
    # new source).
    assert isinstance(body["temperature_trend"], list) and len(body["temperature_trend"]) > 0
    assert len(body["temperature_trend"]) == len(body["temperature_trend_timestamps"])
    assert isinstance(body["humidity_trend"], list) and len(body["humidity_trend"]) > 0
    assert len(body["humidity_trend"]) == len(body["humidity_trend_timestamps"])
    # P2.1: 4 more free KPI tiles (wind speed/direction, surface pressure, UV).
    for key in ("wind_speed", "wind_direction", "surface_pressure", "uv_index"):
        assert body[key] is not None
        assert isinstance(body[f"{key}_trend"], list) and len(body[f"{key}_trend"]) > 0
        assert len(body[f"{key}_trend"]) == len(body[f"{key}_trend_timestamps"])


def test_environmental_summary_is_honestly_empty_for_a_non_demo_city(client, admin_token, db_session):
    """Session 018: ?city_id= for a consortium city with no live connector
    must not silently return Toulouse's readings under a different city's
    label — see app/services/city_context.py."""
    from sqlalchemy import select

    from app.models.geography import City
    from app.seed.seed_geography import run as seed_geography_run

    seed_geography_run()
    ghent = db_session.execute(select(City).where(City.label_en == "Ghent")).scalar_one()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/v1/environmental/summary?city_id={ghent.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_available"] is False
    assert body["monitored_stations"] == 0
    assert body["water_level"] is None
    assert body["water_level_trend"] == []
    assert body["planned_data_source"] == "Waterinfo.be (VMM / MOW-HIC)"


def test_environmental_summary_endpoint_custom_time_range(client, admin_token):
    # P2.1 (D017): the trend window is caller-selectable via `?hours=`.
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/v1/environmental/summary?hours=96", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["trend_window_hours"] == 96
    # A wider window must never return FEWER points than the narrower default
    # (48h backfill data is a strict subset of the 96h window).
    resp_default = client.get("/api/v1/environmental/summary", headers=headers)
    assert len(body["temperature_trend"]) >= len(resp_default.json()["temperature_trend"])
    # Out-of-bounds values are rejected (same bounds as station_timeseries).
    assert client.get("/api/v1/environmental/summary?hours=0", headers=headers).status_code == 422
    assert client.get("/api/v1/environmental/summary?hours=200", headers=headers).status_code == 422


def test_environmental_endpoints_require_authentication(client):
    assert client.get("/api/v1/environmental/sources").status_code == 401
    assert client.get("/api/v1/environmental/stations").status_code == 401
    assert client.get("/api/v1/environmental/summary").status_code == 401


# --- Session 020: DataSource <-> City association, dynamic has_live_data,
# and the write-only credentials endpoint ---


class _CityScopedConnector(BaseConnector):
    """Minimal fake connector for exercising get_or_create_data_source's
    city_id auto-link and run_connector's has_live_data flip, independent
    of any real external API."""

    provider = DataSourceProvider.HUBEAU_HYDROMETRIE
    kind = DataSourceKind.HYDROLOGY
    license = "test"
    homepage_url = "http://example.invalid"
    expected_interval_seconds = 300
    stale_after_seconds = 3600

    def __init__(self, source_code: str, city: str, fail: bool = False) -> None:
        self.source_code = source_code
        self.source_name = f"Test connector for {city}"
        self.city = city
        self.fail = fail

    def fetch(self) -> list[NormalizedReading]:
        if self.fail:
            raise ConnectorError("simulated failure")
        now = datetime.now(timezone.utc)
        return [
            NormalizedReading(
                "CITYTEST1", "City Test Station", StationKind.RIVER_GAUGE, self.city, None, 1.0, 1.0,
                MeasurementVariable.WATER_LEVEL_MM, 100.0, "mm", now,
            )
        ]


def test_get_or_create_data_source_auto_links_city_id(db_session):
    from sqlalchemy import select

    from app.models.geography import City

    toulouse = db_session.execute(select(City).where(City.label_en == "Toulouse")).scalar_one()
    connector = _CityScopedConnector("test_city_link_source", "Toulouse")
    source = get_or_create_data_source(db_session, connector)
    assert source.city_id == toulouse.id


def test_run_connector_flips_city_has_live_data_on_first_success_and_stays_flipped(db_session):
    from sqlalchemy import select

    from app.models.geography import City

    # Athens has no connector anywhere in the app — safe to use as a
    # standalone "was never live" city for this test.
    connector = _CityScopedConnector("test_athens_source", "Athens")
    result = run_connector(db_session, connector)
    assert result["ok"] is True

    athens = db_session.execute(select(City).where(City.label_en == "Athens")).scalar_one()
    assert athens.has_live_data is True
    assert athens.planned_data_source is None

    # A later failure of the same source must not un-flip the city — same
    # "fresh/stale/degraded", never a hard on/off, philosophy as source health.
    failing_connector = _CityScopedConnector("test_athens_source", "Athens", fail=True)
    fail_result = run_connector(db_session, failing_connector)
    assert fail_result["ok"] is False
    db_session.refresh(athens)
    assert athens.has_live_data is True


def test_update_source_credentials_encrypts_and_never_echoes_key(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}
    sources = client.get("/api/v1/environmental/sources", headers=headers).json()
    hubeau_id = next(s["id"] for s in sources if s["code"] == "hubeau_hydrometrie_toulouse_garonne")

    resp = client.put(
        f"/api/v1/environmental/sources/{hubeau_id}/credentials",
        json={"api_key": "super-secret-key"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" not in body
    assert "super-secret-key" not in resp.text
    assert body["is_key_configured"] is True

    source = db_session.query(DataSource).filter_by(code="hubeau_hydrometrie_toulouse_garonne").one()
    assert source.encrypted_api_key is not None
    assert source.encrypted_api_key != "super-secret-key"


def test_update_source_credentials_404_for_unknown_source(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(
        "/api/v1/environmental/sources/00000000-0000-0000-0000-000000000000/credentials",
        json={"api_key": "x"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_sources_endpoint_reports_city_and_requires_api_key(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    sources = client.get("/api/v1/environmental/sources", headers=headers).json()
    hubeau = next(s for s in sources if s["code"] == "hubeau_hydrometrie_toulouse_garonne")
    assert hubeau["city"]["label_en"] == "Toulouse"
    assert hubeau["requires_api_key"] is False
