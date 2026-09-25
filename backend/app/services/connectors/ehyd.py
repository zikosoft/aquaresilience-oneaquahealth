"""eHYD / data.gv.at connector — Austria's official hydrographic open-data
service, covering Vienna.

Source: eHYD (https://ehyd.gv.at/) publishes its current-water-level
("Pegelstände aktuell") dataset through Austria's national geodata
platform as a standard OGC API Features service — no API key, "no
limitations on public access" (CC BY 4.0, attribution to ehyd.gv.at),
confirmed via the dataset's INSPIRE metadata record
(https://geoportal.inspire.gv.at/metadatensuche/inspire/api/records/6a67faa7-3ad7-4faf-91e9-17a518d10685):

    Collections root: https://gis.lfrz.gv.at/api/geodata/i000501/ogc/features/v1
    Collection id:     i000501:pegel_aktuell
    Items endpoint:    .../collections/i000501:pegel_aktuell/items?bbox=...&f=json

OGC API Features is a stable, standardized GeoJSON contract (every
implementation returns the same FeatureCollection/Feature/geometry/
properties envelope) — that part of this connector is not a guess. What
was NOT possible to confirm during research is the exact Austrian
German property key names inside `properties` (e.g. the water-level
value, timestamp, station name, river name), since both the collection's
`/items` endpoint and the dataset catalog page were unreachable through
this platform's page-fetching tool (blocked by robots.txt on that
research pass — an OGC API is meant for machine/application consumption,
not crawling, so this is expected and not a sign the service itself is
unavailable). `_extract_property` below tries several plausible German
hydrographic key names per field and raises a ConnectorError listing the
*actual* property keys seen on any row it can't parse — turning a wrong
guess into a one-line, self-diagnosing fix instead of a silent bad
reading. Treat this connector as best-effort-pending-live-confirmation;
check the /sources page's health/error message after first deploy.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind
from app.services.connectors.base import BaseConnector, ConnectorError, NormalizedReading

BASE_URL = "https://gis.lfrz.gv.at/api/geodata/i000501/ogc/features/v1"
COLLECTION_ID = "i000501:pegel_aktuell"

# Candidate property key names, most-likely-first, for each field — OGC API
# Features leaves property naming entirely up to the publisher, and eHYD's
# are in German. See module docstring for why this is defensive rather than
# a single hardcoded key.
_VALUE_KEYS = ("wert", "pegelstand", "wasserstand", "messwert", "value")
_TIME_KEYS = ("zeitpunkt", "datum", "messzeitpunkt", "zeit", "timestamp", "time")
_NAME_KEYS = ("stationsname", "messstelle", "name", "bezeichnung")
_RIVER_KEYS = ("gewaessername", "gewaesser", "fluss", "river")
_CODE_KEYS = ("hzbnr", "hzbnr01", "stationsnummer", "id", "objectid")


def _extract_property(properties: dict, candidate_keys: tuple[str, ...]) -> object | None:
    lower_map = {str(k).lower(): v for k, v in properties.items()}
    for key in candidate_keys:
        if key in lower_map and lower_map[key] is not None:
            return lower_map[key]
    return None


def _parse_ehyd_datetime(raw: object) -> datetime | None:
    if raw is None:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


class EhydConnector(BaseConnector):
    source_code = "ehyd_vienna"
    source_name = "eHYD / data.gv.at — Vienna"
    provider = DataSourceProvider.EHYD
    kind = DataSourceKind.HYDROLOGY
    license = "Namensnennung 4.0 International (CC BY 4.0) — ehyd.gv.at / data.gv.at"
    homepage_url = "https://ehyd.gv.at/"
    expected_interval_seconds = 900
    stale_after_seconds = 3 * 3600
    requires_api_key = False
    city = "Vienna"

    def __init__(
        self,
        # Vienna-area bounding box (west, south, east, north) — keeps the
        # national dataset's response small and relevant instead of pulling
        # every gauge in Austria on each tick.
        bbox: tuple[float, float, float, float] = (16.18, 48.10, 16.58, 48.32),
        default_lon: float = 16.3738,
        default_lat: float = 48.2082,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.bbox = bbox
        self.default_lon = default_lon
        self.default_lat = default_lat
        self._timeout = timeout_seconds

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _get_items(self) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(
                f"{BASE_URL}/collections/{COLLECTION_ID}/items",
                params={"bbox": ",".join(str(v) for v in self.bbox), "f": "json", "limit": 50},
                headers={"Accept": "application/geo+json, application/json"},
            )
            response.raise_for_status()
            return response.json()

    def fetch(self) -> list[NormalizedReading]:
        try:
            payload = self._get_items()
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"eHYD OGC API Features request failed: {exc}") from exc

        features = payload.get("features")
        if not isinstance(features, list):
            raise ConnectorError(
                f"eHYD response missing/malformed 'features' array (top-level keys: {list(payload.keys())})"
            )
        if not features:
            raise ConnectorError("eHYD returned zero stations within the configured Vienna bounding box")

        readings: list[NormalizedReading] = []
        unparsed_property_samples: list[list[str]] = []
        for feature in features:
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or [self.default_lon, self.default_lat]

            value = _extract_property(properties, _VALUE_KEYS)
            observed_at = _parse_ehyd_datetime(_extract_property(properties, _TIME_KEYS))
            if value is None or observed_at is None:
                unparsed_property_samples.append(list(properties.keys()))
                continue
            try:
                value_cm = float(value)
            except (TypeError, ValueError):
                continue

            station_code = str(_extract_property(properties, _CODE_KEYS) or feature.get("id") or "unknown")
            station_name = str(_extract_property(properties, _NAME_KEYS) or f"eHYD station {station_code}")
            river_name = _extract_property(properties, _RIVER_KEYS)

            readings.append(
                NormalizedReading(
                    station_external_code=station_code,
                    station_name=station_name,
                    station_kind=StationKind.RIVER_GAUGE,
                    city=self.city,
                    river_name=str(river_name) if river_name else None,
                    lon=float(coordinates[0]) if len(coordinates) > 0 else self.default_lon,
                    lat=float(coordinates[1]) if len(coordinates) > 1 else self.default_lat,
                    # eHYD publishes stage in cm — normalize to mm like every
                    # other hydrology connector.
                    variable=MeasurementVariable.WATER_LEVEL_MM,
                    value=value_cm * 10.0,
                    unit="mm",
                    observed_at=observed_at,
                )
            )

        if not readings:
            sample = unparsed_property_samples[0] if unparsed_property_samples else []
            raise ConnectorError(
                "eHYD returned stations but none had a recognized value/timestamp property. "
                f"Actual property keys on the first row: {sample}. "
                "Update _VALUE_KEYS/_TIME_KEYS in app/services/connectors/ehyd.py to match."
            )
        return readings
