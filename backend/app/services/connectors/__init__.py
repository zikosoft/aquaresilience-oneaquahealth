"""Connector registry: every configured external data source, in one place.

Adding a new source means writing one `BaseConnector` subclass and adding it
to this list — nothing else in the ingestion pipeline, API, or frontend
needs to change (per the P1 "reusable connector interface" requirement).
"""
from __future__ import annotations

from app.services.connectors.base import BaseConnector
from app.services.connectors.hubeau import HubeauHydrometrieConnector
from app.services.connectors.open_meteo import OpenMeteoConnector


def get_connectors() -> list[BaseConnector]:
    return [
        HubeauHydrometrieConnector(),
        OpenMeteoConnector(),
    ]


__all__ = ["BaseConnector", "HubeauHydrometrieConnector", "OpenMeteoConnector", "get_connectors"]
