"""Hub'Eau Hydrométrie connector — French official open hydrology data.

Source: https://hubeau.eaufrance.fr/page/api-hydrometrie (Eaufrance / French
Ministry for Ecological Transition). Public, free, no API key or
registration required. Real-time water-height observations are published
roughly every 5 minutes for ~5,000 French hydrometric stations.

Station used for the Toulouse demo geography: O200004001 — "La Garonne à
Toulouse [Pont-Neuf] - Quai de Tounis", confirmed live via the API during
development (real observations returned, coordinates ~1.44E/43.60N, right on
the Toulouse city-centre stretch of the Garonne that the platform's default
map viewport is centered on).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie"


def _parse_hubeau_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Hub'Eau returns e.g. "2026-09-21T23:15:00Z".
        value = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


class HubeauHydrometrieConnector(BaseConnector):
    source_code = "hubeau_hydrometrie_toulouse_garonne"
    source_name = "Hub'Eau Hydrométrie — Garonne à Toulouse"
    provider = DataSourceProvider.HUBEAU_HYDROMETRIE
    kind = DataSourceKind.HYDROLOGY
    license = "Licence Ouverte / Open Licence 2.0 (Etalab) — hubeau.eaufrance.fr"
    homepage_url = "https://hubeau.eaufrance.fr/page/api-hydrometrie"
    # Hub'Eau publishes real-time height roughly every 5 minutes; allow a
    # generous margin before calling it stale (upstream gaps of 20-30 min
    # during station maintenance are routine and not a platform failure).
    expected_interval_seconds = 300
    stale_after_seconds = 3600

    def __init__(
        self,
        station_code: str = "O200004001",
        station_name: str = "La Garonne à Toulouse [Pont-Neuf] - Quai de Tounis",
        city: str = "Toulouse",
        river_name: str = "Garonne",
        default_lon: float = 1.4442,
        default_lat: float = 43.6047,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.station_code = station_code
        self.station_name = station_name
        self.city = city
        self.river_name = river_name
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
            response = client.get(f"{BASE_URL}/{path}", params=params)
            response.raise_for_status()
            return response.json()

    def fetch(self) -> list[NormalizedReading]:
        try:
            payload = self._get(
                "observations_tr",
                {
                    "code_entite": self.station_code,
                    "grandeur_hydro": "H",
                    "size": 50,
                    "sort": "desc",
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"Hub'Eau hydrometrie request failed: {exc}") from exc

        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise ConnectorError("Hub'Eau hydrometrie response missing/malformed 'data' array")

        readings: list[NormalizedReading] = []
        for row in rows:
            observed_at = _parse_hubeau_datetime(row.get("date_obs"))
            value = row.get("resultat_obs")
            if observed_at is None or value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            readings.append(
                NormalizedReading(
                    station_external_code=self.station_code,
                    station_name=self.station_name,
                    station_kind=StationKind.RIVER_GAUGE,
                    city=self.city,
                    river_name=self.river_name,
                    lon=float(row.get("longitude") or self.default_lon),
                    lat=float(row.get("latitude") or self.default_lat),
                    variable=MeasurementVariable.WATER_LEVEL_MM,
                    value=value,
                    unit="mm",
                    observed_at=observed_at,
                )
            )
        if not readings and rows:
            # The upstream call succeeded and returned rows, but none of them
            # parsed — that is a real data-quality problem worth surfacing as
            # a failed ingestion attempt rather than silently reporting zero
            # new measurements.
            raise ConnectorError("Hub'Eau hydrometrie returned rows but none had a usable date_obs/resultat_obs")
        return readings
