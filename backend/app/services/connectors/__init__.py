"""Connector registry: every configured external data source, in one place.

Adding a new source means writing one `BaseConnector` subclass and adding it
to this list — nothing else in the ingestion pipeline, API, or frontend
needs to change (per the P1 "reusable connector interface" requirement).

Session 020 (user request): now DB-aware. NveHydapiConnector (the one
connector that needs an API key) is registered UNCONDITIONALLY, key or no
key — its own `fetch()` raises a clear, self-explaining ConnectorError when
`api_key` is None, which `run_connector` records as a normal failed
attempt (degraded health, no crash), exactly like any other misconfigured
source. This is deliberate, not an oversight: a DataSource row only ever
gets created by `get_or_create_data_source`, which only ever runs for
connectors THIS function returns — so gating the connector itself on "a
key already exists" would mean the row (and with it, the /sources page's
"Add API key" button) could never appear in the first place. The platform
cannot self-register a key (that needs a human at hydapi.nve.no/Users, see
the app's own safety rules on account creation); pasting one in via
`PUT /environmental/sources/{id}/credentials` is what the next tick then
picks up automatically, no redeploy. Vienna/Ghent's connectors are keyless
and always fetch successfully-or-not on their own. Oslo's *weather*
counterpart, unlike its hydrology one, stays gated behind a configured key
— see the comment below for why.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.environmental import DataSource
from app.services.connectors.base import BaseConnector
from app.services.connectors.ehyd import EhydConnector
from app.services.connectors.hubeau import HubeauHydrometrieConnector
from app.services.connectors.nve_hydapi import NveHydapiConnector
from app.services.connectors.open_meteo import OpenMeteoConnector
from app.services.connectors.waterinfo_be import WaterinfoConnector


def _stored_api_key(db: Session, source_code: str) -> str | None:
    source = db.execute(select(DataSource).where(DataSource.code == source_code)).scalar_one_or_none()
    if source is None or not source.encrypted_api_key:
        return None
    return decrypt_secret(source.encrypted_api_key)


def get_connectors(db: Session) -> list[BaseConnector]:
    connectors: list[BaseConnector] = [
        HubeauHydrometrieConnector(),
        OpenMeteoConnector(),
        # Vienna (eHYD) — keyless, registered unconditionally.
        EhydConnector(),
        OpenMeteoConnector(lon=16.3738, lat=48.2082, city="Vienna"),
        # Ghent (Waterinfo.be) — keyless for light polling; an optional
        # token (stored the same encrypted way) raises the rate allowance.
        WaterinfoConnector(api_key=_stored_api_key(db, "waterinfo_be_ghent")),
        OpenMeteoConnector(lon=3.7174, lat=51.0543, city="Ghent"),
    ]

    # Oslo (NVE HydAPI) — always registered so its DataSource row exists
    # and the /sources page can show "API key required" + accept one (see
    # module docstring). fetch() itself fails cleanly without a key.
    nve_key = _stored_api_key(db, "nve_hydapi_oslo")
    connectors.append(NveHydapiConnector(api_key=nve_key))
    # Its weather counterpart, unlike Vienna/Ghent's, stays gated behind
    # the key: run_connector flips City.has_live_data on ANY successful
    # source for that city, and Open-Meteo alone would succeed even while
    # hydrology keeps failing — showing Oslo as "live" with weather charts
    # but no water level, which is exactly the misleading half-live state
    # the honesty pattern (app.services.city_context.resolve_city) exists
    # to prevent. Both go live together, once a key makes that possible.
    if nve_key:
        connectors.append(OpenMeteoConnector(lon=10.7522, lat=59.9139, city="Oslo"))

    return connectors


__all__ = [
    "BaseConnector",
    "HubeauHydrometrieConnector",
    "OpenMeteoConnector",
    "EhydConnector",
    "WaterinfoConnector",
    "NveHydapiConnector",
    "get_connectors",
]
