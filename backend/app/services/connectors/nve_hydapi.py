"""NVE HydAPI connector — Norwegian Water Resources and Energy Directorate's
official hydrological data API, covering Oslo.

Source: https://hydapi.nve.no/ (docs: https://hydapi.nve.no/UserDocumentation/,
interactive reference: https://hydapi.nve.no/swagger/index.html?urls.primaryName=V1).
REST/JSON, ~1,800 stations nationwide, licensed under the Norwegian Public
Data License (NLOD, CC BY 3.0-compatible). Unlike Hub'Eau, this one REQUIRES
a registered API key — free, self-service, generated instantly at
https://hydapi.nve.no/Users (tied to an email address; the platform cannot
register this on a user's behalf, see the app's own safety rules on account
creation). Confirmed live during research: an unauthenticated request to
/api/v1/Stations correctly returns 401 rather than a network/DNS error.

Deliberately does not hardcode a station code the way HubeauHydrometrieConnector
does for Toulouse's Garonne gauge — NVE's own station list was not directly
browsable without a key during research, so this queries `/Stations` by
municipality (CouncilName=Oslo) at fetch time and picks the first active
station exposing a water-level series (Parameter 1000), then reads its
latest observations. This also means the connector never goes stale just
because a specific station is decommissioned — NVE's municipality filter
does that redirection for free.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

BASE_URL = "https://hydapi.nve.no/api/v1"

# NVE's own parameter code for water stage/level (see /api/v1/Parameters).
WATER_LEVEL_PARAMETER = "1000"


def _parse_nve_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


class NveHydapiConnector(BaseConnector):
    source_code = "nve_hydapi_oslo"
    source_name = "NVE HydAPI — Oslo"
    provider = DataSourceProvider.NVE_HYDAPI
    kind = DataSourceKind.HYDROLOGY
    license = "Norsk lisens for offentlige data (NLOD) — hydapi.nve.no"
    homepage_url = "https://hydapi.nve.no/"
    # NVE recommends polling series-metadata roughly every 10 min; real-time
    # water-level series typically update sub-hourly, so this stays in the
    # same ballpark as Hub'Eau rather than NVE's own (looser) metadata cadence.
    expected_interval_seconds = 900
    stale_after_seconds = 3 * 3600
    requires_api_key = True
    city = "Oslo"

    def __init__(
        self,
        api_key: str | None,
        council_name: str = "Oslo",
        default_lon: float = 10.7522,
        default_lat: float = 59.9139,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.council_name = council_name
        self.default_lon = default_lon
        self.default_lat = default_lat
        self._timeout = timeout_seconds

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _get(self, path: str, params: dict) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(
                f"{BASE_URL}/{path}",
                params=params,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    def _find_station(self) -> dict:
        try:
            payload = self._get(
                "Stations",
                {"CouncilName": self.council_name, "Active": "OnlyActive"},
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"NVE HydAPI /Stations request failed: {exc}") from exc

        stations = payload.get("data", [])
        if not isinstance(stations, list) or not stations:
            raise ConnectorError(f"NVE HydAPI returned no stations for CouncilName={self.council_name}")

        candidates = [
            s
            for s in stations
            if s.get("stationId")
            and any(str(series.get("parameter")) == WATER_LEVEL_PARAMETER for series in (s.get("seriesList") or []))
        ]
        if candidates:
            def _squared_distance_to_city(s: dict) -> float:
                lon, lat = s.get("longitude"), s.get("latitude")
                if lon is None or lat is None:
                    return float("inf")
                return (float(lon) - self.default_lon) ** 2 + (float(lat) - self.default_lat) ** 2

            return min(candidates, key=_squared_distance_to_city)
        # Fall back to the first active station even without a confirmed
        # water-level series listing — still worth surfacing rather than
        # failing outright, since seriesList isn't always populated.
        if stations[0].get("stationId"):
            return stations[0]
        raise ConnectorError("NVE HydAPI station list rows are missing stationId")

    def fetch(self) -> list[NormalizedReading]:
        if not self.api_key:
            raise ConnectorError(
                "NVE HydAPI requires a registered API key — none is configured for this source yet. "
                "Register a free key at https://hydapi.nve.no/Users and add it via the Data Sources page."
            )

        station = self._find_station()
        station_id = station["stationId"]
        station_name = station.get("stationName") or f"NVE station {station_id}"
        lon = float(station.get("longitude") or self.default_lon)
        lat = float(station.get("latitude") or self.default_lat)

        try:
            payload = self._get(
                "Observations",
                {"StationId": station_id, "Parameter": WATER_LEVEL_PARAMETER, "ResolutionTime": 0},
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"NVE HydAPI /Observations request failed: {exc}") from exc

        series_rows = payload.get("data", [])
        if not isinstance(series_rows, list):
            raise ConnectorError("NVE HydAPI /Observations response missing/malformed 'data' array")

        readings: list[NormalizedReading] = []
        for series in series_rows:
            unit = series.get("unit") or "cm"
            for obs in series.get("observations", []):
                observed_at = _parse_nve_datetime(obs.get("time"))
                value = obs.get("value")
                if observed_at is None or value is None:
                    continue
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                # NVE reports stage in cm by default; normalize to mm to
                # match every other hydrology connector's variable unit.
                value_mm = value * 10.0 if unit.lower() == "cm" else value
                readings.append(
                    NormalizedReading(
                        station_external_code=str(station_id),
                        station_name=station_name,
                        station_kind=StationKind.RIVER_GAUGE,
                        city=self.city,
                        river_name=station.get("riverName"),
                        lon=lon,
                        lat=lat,
                        variable=MeasurementVariable.WATER_LEVEL_MM,
                        value=value_mm,
                        unit="mm",
                        observed_at=observed_at,
                    )
                )
        if not readings:
            raise ConnectorError(
                f"NVE HydAPI station {station_id} ({station_name}) returned no usable water-level observations"
            )
        return readings
