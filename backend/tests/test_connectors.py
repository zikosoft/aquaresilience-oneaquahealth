"""Session 020 — parsing/behavior tests for the 3 new consortium-city
connectors (Vienna/eHYD, Ghent/Waterinfo.be, Oslo/NVE HydAPI). None of
these hit the real network: each connector's own `_get`/`_get_items`
HTTP method is monkeypatched with realistic canned payloads, the same
pattern `test_environmental.py`'s `_FakeConnector` uses one level up
(swap the whole connector, here we swap just the HTTP call and exercise
the real parsing code).

For eHYD/Waterinfo.be specifically, the exact live response shape could
not be independently confirmed during research (see each connector
module's own docstring) — these fixtures encode the best-effort,
standards-based shape each connector was written against, so what's
actually under test is "does the parser correctly handle a payload in
that shape", not "is that shape provably what the live API returns
today". The connectors' own defensive fallbacks (case-insensitive
multi-candidate property matching, clear ConnectorError messages citing
the actual keys seen) are what should catch a real mismatch cheaply
after first live deploy.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.environmental import MeasurementVariable
from app.services.connectors.base import ConnectorError
from app.services.connectors.ehyd import EhydConnector
from app.services.connectors.nve_hydapi import NveHydapiConnector
from app.services.connectors.waterinfo_be import WaterinfoConnector


# --- NVE HydAPI (Oslo) ---

def test_nve_connector_raises_clearly_when_no_api_key_configured():
    connector = NveHydapiConnector(api_key=None)
    with pytest.raises(ConnectorError, match="requires a registered API key"):
        connector.fetch()


def test_nve_connector_parses_stations_and_observations(monkeypatch):
    connector = NveHydapiConnector(api_key="test-key")

    responses = {
        "Stations": {
            "data": [
                {
                    "stationId": "6.10.0",
                    "stationName": "Gryta",
                    "latitude": 59.91,
                    "longitude": 10.75,
                    "riverName": "Akerselva",
                    "seriesList": [{"parameter": "1000"}],
                }
            ]
        },
        "Observations": {
            "data": [
                {
                    "stationId": "6.10.0",
                    "unit": "cm",
                    "observations": [
                        {"time": "2026-09-25T10:00:00Z", "value": 42.5},
                        {"time": "2026-09-25T09:45:00Z", "value": 42.0},
                    ],
                }
            ]
        },
    }

    def fake_get(self, path, params):
        return responses[path]

    monkeypatch.setattr(NveHydapiConnector, "_get", fake_get)

    readings = connector.fetch()
    assert len(readings) == 2
    assert readings[0].station_external_code == "6.10.0"
    assert readings[0].station_name == "Gryta"
    assert readings[0].river_name == "Akerselva"
    assert readings[0].variable == MeasurementVariable.WATER_LEVEL_MM
    assert readings[0].unit == "mm"
    # 42.5 cm -> 425 mm
    assert readings[0].value == pytest.approx(425.0)
    assert readings[0].observed_at == datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def test_nve_connector_raises_when_no_stations_in_council(monkeypatch):
    connector = NveHydapiConnector(api_key="test-key")
    monkeypatch.setattr(NveHydapiConnector, "_get", lambda self, path, params: {"data": []})
    with pytest.raises(ConnectorError, match="no stations"):
        connector.fetch()


# --- eHYD (Vienna) ---

def test_ehyd_connector_parses_geojson_features(monkeypatch):
    connector = EhydConnector()

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "207357",
                "geometry": {"type": "Point", "coordinates": [16.37, 48.21]},
                "properties": {
                    "HZBNR": "207357",
                    "Stationsname": "Wien - Donaukanal",
                    "Gewaessername": "Donaukanal",
                    "Wert": "185.4",
                    "Zeitpunkt": "2026-09-25T11:00:00+02:00",
                },
            }
        ],
    }
    monkeypatch.setattr(EhydConnector, "_get_items", lambda self: payload)

    readings = connector.fetch()
    assert len(readings) == 1
    r = readings[0]
    assert r.station_external_code == "207357"
    assert r.station_name == "Wien - Donaukanal"
    assert r.river_name == "Donaukanal"
    assert r.lon == pytest.approx(16.37)
    assert r.lat == pytest.approx(48.21)
    # 185.4 cm -> 1854 mm
    assert r.value == pytest.approx(1854.0)
    assert r.unit == "mm"


def test_ehyd_connector_raises_self_diagnosing_error_on_unrecognized_properties(monkeypatch):
    connector = EhydConnector()
    payload = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"someUnexpectedKey": "x"}, "geometry": {}}],
    }
    monkeypatch.setattr(EhydConnector, "_get_items", lambda self: payload)

    with pytest.raises(ConnectorError, match="someUnexpectedKey"):
        connector.fetch()


def test_ehyd_connector_raises_when_no_features_in_bbox(monkeypatch):
    connector = EhydConnector()
    monkeypatch.setattr(EhydConnector, "_get_items", lambda self: {"features": []})
    with pytest.raises(ConnectorError, match="zero stations"):
        connector.fetch()


# --- Waterinfo.be (Ghent) ---

def test_waterinfo_connector_parses_station_timeseries_and_values(monkeypatch):
    connector = WaterinfoConnector()

    call_log: list[dict] = []

    def fake_get(self, params):
        call_log.append(params)
        request = params["request"]
        if request == "getStationList":
            return [
                {
                    "station_no": "GNT01",
                    "station_name": "Gent - Ringvaart",
                    "station_latitude": "51.05",
                    "station_longitude": "3.72",
                }
            ]
        if request == "getTimeseriesList":
            return [
                {"ts_id": "999", "ts_name": "Waterstand.Ruw", "parametertype_name": "Waterstand"},
            ]
        if request == "getTimeseriesValues":
            return [
                {
                    "ts_id": "999",
                    "columns": "Timestamp,Value",
                    "data": [
                        ["2026-09-25T10:00:00.000+02:00", 61.2],
                        ["2026-09-25T09:45:00.000+02:00", 60.8],
                    ],
                }
            ]
        raise AssertionError(f"unexpected request {request}")

    monkeypatch.setattr(WaterinfoConnector, "_get", fake_get)

    readings = connector.fetch()
    assert len(readings) == 2
    assert readings[0].station_external_code == "GNT01"
    assert readings[0].station_name == "Gent - Ringvaart"
    # 61.2 cm -> 612 mm
    assert readings[0].value == pytest.approx(612.0)
    assert readings[0].unit == "mm"
    # No token configured -> no `token` param sent.
    assert all("token" not in p for p in call_log)


def test_waterinfo_connector_sends_token_when_configured(monkeypatch):
    connector = WaterinfoConnector(api_key="secret-token")
    seen_tokens = []

    def fake_get(self, params):
        seen_tokens.append(params.get("token"))
        if params["request"] == "getStationList":
            return [{"station_no": "GNT01", "station_name": "Gent"}]
        if params["request"] == "getTimeseriesList":
            return [{"ts_id": "1", "parametertype_name": "Waterstand"}]
        return [{"ts_id": "1", "columns": "Timestamp,Value", "data": [["2026-09-25T10:00:00+02:00", 50.0]]}]

    monkeypatch.setattr(WaterinfoConnector, "_get", fake_get)
    connector.fetch()
    assert seen_tokens == ["secret-token", "secret-token", "secret-token"]


def test_waterinfo_connector_raises_when_no_station_found(monkeypatch):
    connector = WaterinfoConnector()
    monkeypatch.setattr(WaterinfoConnector, "_get", lambda self, params: [])
    with pytest.raises(ConnectorError, match="no stations matching"):
        connector.fetch()
