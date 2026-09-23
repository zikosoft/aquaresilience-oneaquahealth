"""P1 — environmental data: sources, stations, timeseries, summary, and the
ingestion pipeline's idempotency/health-computation guarantees."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.environmental import DataSource, DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading
from app.services.ingestion_service import SourceHealth, compute_source_health, run_connector


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

    def fetch(self) -> list[NormalizedReading]:
        if self.fail:
            raise ConnectorError("simulated failure")
        now = datetime.now(timezone.utc).replace(microsecond=0)
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
