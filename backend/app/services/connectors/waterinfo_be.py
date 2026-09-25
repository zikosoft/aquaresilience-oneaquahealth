"""Waterinfo.be connector — Flanders' official water-level service (VMM /
Vlaamse Waterweg), covering Ghent.

Source: https://waterinfo.vlaanderen.be/ / https://www.waterinfo.be/, built
on KISTERS' KiWIS platform (confirmed via the actively-maintained Python
wrapper package `pywaterinfo`, https://github.com/fluves/pywaterinfo, which
documents: no token required for "limited and irregular downloads"; a free
client-credit token — requested by emailing hydrometrie@waterinfo.be — is
recommended only for substantial/production-volume polling. This connector
works without a token; `api_key` is accepted and, when configured via the
Data Sources page, sent as the standard KiWIS `token=` parameter for a
higher, more reliable rate allowance).

KiWIS is a standardized product deployed by many national water agencies
(not a Flanders-specific one-off), so its request/response contract is
stable and well-documented independent of this specific deployment:
`request=getStationList` / `request=getTimeseriesList` /
`request=getTimeseriesValues`, JSON responses shaped as a `columns` header
string plus a `data` array-of-arrays. The exact base URL
(`download.waterinfo.be/timeseries/KiWIS/KiWIS`, matching pywaterinfo's
documented default) was not independently re-confirmed against a live raw
response during research (blocked by robots.txt on this platform's
page-fetching tool, same caveat as EhydConnector — see that module's
docstring). Treat as best-effort-pending-live-confirmation; a structural
mismatch raises ConnectorError with the actual response shape observed,
for a fast one-line fix rather than a silent bad reading.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

BASE_URL = "https://download.waterinfo.be/timeseries/KiWIS/KiWIS"


def _parse_kiwis_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


class WaterinfoConnector(BaseConnector):
    source_code = "waterinfo_be_ghent"
    source_name = "Waterinfo.be — Ghent"
    provider = DataSourceProvider.WATERINFO_BE
    kind = DataSourceKind.HYDROLOGY
    license = "Vlaamse open data licentie (free reuse, attribution) — waterinfo.be"
    homepage_url = "https://www.waterinfo.be/"
    expected_interval_seconds = 900
    stale_after_seconds = 3 * 3600
    # Not gated on a key (works keyless for light polling) — see module
    # docstring — so this stays False even though `api_key` is accepted.
    requires_api_key = False
    city = "Ghent"

    def __init__(
        self,
        api_key: str | None = None,
        station_name_pattern: str = "*Gent*",
        default_lon: float = 3.7174,
        default_lat: float = 51.0543,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.station_name_pattern = station_name_pattern
        self.default_lon = default_lon
        self.default_lat = default_lat
        self._timeout = timeout_seconds

    def _base_params(self) -> dict:
        params = {"service": "kisters", "type": "queryServices", "datasource": 0, "format": "json"}
        if self.api_key:
            params["token"] = self.api_key
        return params

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _get(self, params: dict) -> object:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    def _find_station(self) -> dict:
        try:
            payload = self._get(
                {
                    **self._base_params(),
                    "request": "getStationList",
                    "station_name": self.station_name_pattern,
                    "returnfields": "station_no,station_id,station_name,station_latitude,station_longitude",
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Waterinfo.be getStationList request failed: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise ConnectorError(f"Waterinfo.be returned no stations matching '{self.station_name_pattern}'")
        # KiWIS's JSON list responses use the first row as a header when
        # `returnfields` wasn't honored as named dict keys by this
        # deployment — handle both shapes defensively.
        first = payload[0]
        if isinstance(first, dict):
            return first
        if isinstance(first, list) and len(payload) > 1 and isinstance(payload[1], list):
            header = [str(h).lower() for h in first]
            return dict(zip(header, payload[1]))
        raise ConnectorError(f"Waterinfo.be getStationList response has an unrecognized shape: {type(first)}")

    def _find_water_level_timeseries_id(self, station_no: str) -> str:
        try:
            payload = self._get(
                {
                    **self._base_params(),
                    "request": "getTimeseriesList",
                    "station_no": station_no,
                    "returnfields": "ts_id,ts_name,parametertype_name",
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Waterinfo.be getTimeseriesList request failed: {exc}") from exc

        rows = payload if isinstance(payload, list) else []
        candidates = [r for r in rows if isinstance(r, dict)]
        for row in candidates:
            param = str(row.get("parametertype_name") or row.get("ts_name") or "").lower()
            if "waterstand" in param or "water level" in param or "waterhoogte" in param or "level" in param:
                ts_id = row.get("ts_id")
                if ts_id:
                    return str(ts_id)
        if candidates and candidates[0].get("ts_id"):
            return str(candidates[0]["ts_id"])
        raise ConnectorError(f"Waterinfo.be station {station_no} has no timeseries with a usable ts_id")

    def fetch(self) -> list[NormalizedReading]:
        station = self._find_station()
        station_no = str(station.get("station_no") or station.get("station_id") or "")
        station_name = str(station.get("station_name") or f"Waterinfo.be station {station_no}")
        lon = float(station.get("station_longitude") or self.default_lon)
        lat = float(station.get("station_latitude") or self.default_lat)
        if not station_no:
            raise ConnectorError(f"Waterinfo.be station row is missing station_no/station_id: {station}")

        ts_id = self._find_water_level_timeseries_id(station_no)

        try:
            payload = self._get(
                {
                    **self._base_params(),
                    "request": "getTimeseriesValues",
                    "ts_id": ts_id,
                    "period": "P1D",
                    "returnfields": "Timestamp,Value",
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Waterinfo.be getTimeseriesValues request failed: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise ConnectorError("Waterinfo.be getTimeseriesValues returned an empty/unrecognized response")

        series = payload[0] if isinstance(payload[0], dict) else {}
        rows = series.get("data")
        columns_raw = series.get("columns")
        if not isinstance(rows, list) or not columns_raw:
            raise ConnectorError(
                f"Waterinfo.be getTimeseriesValues response missing 'columns'/'data' (keys: {list(series.keys())})"
            )
        columns = [c.strip().lower() for c in str(columns_raw).split(",")]
        try:
            ts_index = columns.index("timestamp")
            value_index = columns.index("value")
        except ValueError as exc:
            raise ConnectorError(f"Waterinfo.be 'columns' did not include Timestamp/Value: {columns}") from exc

        readings: list[NormalizedReading] = []
        for row in rows:
            if not isinstance(row, list) or len(row) <= max(ts_index, value_index):
                continue
            observed_at = _parse_kiwis_datetime(row[ts_index])
            value = row[value_index]
            if observed_at is None or value is None:
                continue
            try:
                value_cm = float(value)
            except (TypeError, ValueError):
                continue
            readings.append(
                NormalizedReading(
                    station_external_code=station_no,
                    station_name=station_name,
                    station_kind=StationKind.RIVER_GAUGE,
                    city=self.city,
                    river_name="Leie" if "gent" in station_name.lower() else None,
                    lon=lon,
                    lat=lat,
                    # KiWIS water-level series are conventionally cm — normalize to mm.
                    variable=MeasurementVariable.WATER_LEVEL_MM,
                    value=value_cm * 10.0,
                    unit="mm",
                    observed_at=observed_at,
                )
            )
        if not readings:
            raise ConnectorError(f"Waterinfo.be timeseries {ts_id} for station {station_no} had no usable rows")
        return readings
