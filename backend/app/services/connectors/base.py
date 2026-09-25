"""Reusable connector interface for external environmental data sources.

Every connector (Hub'Eau, Open-Meteo, and any future source) implements the
same small contract: describe itself (for the `DataSource` row) and return a
flat list of `NormalizedReading`s for `fetch()`. All source-specific HTTP
shape, units, and field-name handling stays inside the connector; nothing
downstream (the ingestion service, the API, the frontend) needs to know
which provider a reading came from.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.models.environmental import DataSourceKind, DataSourceProvider, MeasurementVariable, StationKind


class ConnectorError(Exception):
    """Raised by a connector when a fetch could not be completed.

    Always caught by the ingestion service — it is expected, routine
    behavior (a flaky upstream API), not a bug. The service records it on
    the `DataSource` row (last_error_message, consecutive_failures) and
    leaves previously-ingested measurements in place (last-valid fallback).
    """


@dataclass(frozen=True, slots=True)
class NormalizedReading:
    """One connector-agnostic measurement, ready to persist."""

    station_external_code: str
    station_name: str
    station_kind: StationKind
    city: str
    river_name: str | None
    lon: float
    lat: float
    variable: MeasurementVariable
    value: float
    unit: str
    observed_at: datetime


class BaseConnector(ABC):
    """One configured external connector."""

    # --- Identity / metadata, used to upsert the DataSource row ---
    source_code: str
    source_name: str
    provider: DataSourceProvider
    kind: DataSourceKind
    license: str
    homepage_url: str
    # Expected cadence of new data at the upstream source, and how long a
    # silence can go before the source counts as "stale" — both feed the
    # freshness computation in `ingestion_service.compute_source_health`.
    expected_interval_seconds: int = 900
    stale_after_seconds: int = 3600
    # Session 020: whether fetch() is expected to fail without a configured
    # API key (drives the /sources page's "add API key" prompt and the
    # get_connectors() registration gate — see app/services/connectors/__init__.py).
    requires_api_key: bool = False
    # City this connector's readings belong to — must match a seeded
    # City.label_en exactly (app/models/geography.py) so
    # ingestion_service.get_or_create_data_source can resolve the FK
    # automatically. Declared here (not just as an instance attribute on
    # each connector) so callers can type-check against it.
    city: str = ""

    @abstractmethod
    def fetch(self) -> list[NormalizedReading]:
        """Fetch and normalize the latest readings. Raises ConnectorError on failure."""
        raise NotImplementedError
