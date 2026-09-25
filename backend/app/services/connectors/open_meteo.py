"""Open-Meteo connector — free weather API, no key/registration required.

Source: https://open-meteo.com/ (non-commercial use, no API key needed —
"Only required to commercial use to access reserved API resources").
Provides hourly precipitation, soil moisture, temperature and humidity for
any lat/lon, blending observed and short-range forecast data.

Only hours at-or-before "now" are ingested as measurements (Open-Meteo's
`forecast_days`/`past_days` window also includes genuine future forecast
hours, which are not observations and must not be stored as if they were —
the Scenario Simulator in P4 is the deliberate, explicit place for
projected/what-if values, not the environmental measurement history).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

BASE_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARIABLES = {
    "precipitation": (MeasurementVariable.PRECIPITATION_MM, "mm"),
    "soil_moisture_0_to_1cm": (MeasurementVariable.SOIL_MOISTURE_RATIO, "m3/m3"),
    "temperature_2m": (MeasurementVariable.TEMPERATURE_C, "°C"),
    "relative_humidity_2m": (MeasurementVariable.HUMIDITY_PERCENT, "%"),
    # P2.1: 4 more free hourly fields from the same connector/API — no new
    # source, no key, same ingestion/trend pattern as temperature/humidity.
    "wind_speed_10m": (MeasurementVariable.WIND_SPEED_KMH, "km/h"),
    "wind_direction_10m": (MeasurementVariable.WIND_DIRECTION_DEG, "°"),
    "surface_pressure": (MeasurementVariable.SURFACE_PRESSURE_HPA, "hPa"),
    "uv_index": (MeasurementVariable.UV_INDEX, "index"),
}


class OpenMeteoConnector(BaseConnector):
    source_code = "open_meteo_toulouse"
    source_name = "Open-Meteo — Toulouse"
    provider = DataSourceProvider.OPEN_METEO
    kind = DataSourceKind.WEATHER
    license = "Open-Meteo non-commercial use (CC BY 4.0-compatible attribution) — open-meteo.com"
    homepage_url = "https://open-meteo.com/"
    # Open-Meteo's hourly model updates several times a day; hourly cadence
    # is the right ingestion interval, with a generous stale window since a
    # single missed run is not meaningful for weather (unlike a river gauge).
    expected_interval_seconds = 3600
    stale_after_seconds = 3 * 3600

    def __init__(
        self,
        # Open-Meteo is a gridded weather model, not a physical station, so
        # there is no single "true" coordinate the way there is for the
        # Hub'Eau river gauge. Deliberately offset a few hundred meters from
        # the Garonne gauge's exact point (1.4442, 43.6047) so the two
        # station markers don't render stacked on top of each other on the
        # map (confirmed during testing: identical coordinates made the
        # Hub'Eau marker unclickable, hidden under the Open-Meteo one).
        lon: float = 1.4608,
        lat: float = 43.6112,
        city: str = "Toulouse",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.lon = lon
        self.lat = lat
        self.city = city
        self._timeout = timeout_seconds
        # Session 020 (user request): Open-Meteo needs zero new connector
        # code per city (global gridded model, no key) — but source_code/
        # source_name were fixed class attributes hardcoded to Toulouse, so
        # a second instance for another city would have silently reused (and
        # overwritten the identity of) the same DataSource row. Overriding
        # them as instance attributes here is what actually makes "just
        # instantiate OpenMeteoConnector(city=...)" safe for a new city.
        if city != "Toulouse":
            self.source_code = f"open_meteo_{city.lower()}"
            self.source_name = f"Open-Meteo — {city}"

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _get(self, params: dict) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    def fetch(self) -> list[NormalizedReading]:
        try:
            payload = self._get(
                {
                    "latitude": self.lat,
                    "longitude": self.lon,
                    "hourly": ",".join(HOURLY_VARIABLES.keys()),
                    "timezone": "UTC",
                    "past_days": 1,
                    "forecast_days": 1,
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Open-Meteo request failed: {exc}") from exc

        hourly = payload.get("hourly")
        if not isinstance(hourly, dict) or "time" not in hourly:
            raise ConnectorError("Open-Meteo response missing/malformed 'hourly' block")

        times = hourly.get("time", [])
        now = datetime.now(timezone.utc)
        # Only ingest up through the current hour — later entries in the
        # same response are genuine forecast, not observations.
        cutoff = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        readings: list[NormalizedReading] = []
        for index, raw_time in enumerate(times):
            try:
                observed_at = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if observed_at >= cutoff:
                continue
            for field_name, (variable, unit) in HOURLY_VARIABLES.items():
                series = hourly.get(field_name)
                if not isinstance(series, list) or index >= len(series):
                    continue
                value = series[index]
                if value is None:
                    continue
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                readings.append(
                    NormalizedReading(
                        station_external_code=f"open_meteo_{self.city.lower()}",
                        station_name=f"Open-Meteo — {self.city}",
                        station_kind=StationKind.WEATHER_POINT,
                        city=self.city,
                        river_name=None,
                        lon=self.lon,
                        lat=self.lat,
                        variable=variable,
                        value=value,
                        unit=unit,
                        observed_at=observed_at,
                    )
                )
        if not readings:
            raise ConnectorError("Open-Meteo returned no usable observed (non-forecast) hourly readings")
        return readings
