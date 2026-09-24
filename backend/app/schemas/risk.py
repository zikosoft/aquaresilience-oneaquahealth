from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RiskFactorOut(BaseModel):
    key: str  # rainfall | hydrology | environmental | trend
    label: str
    weight: float  # configured weight, from Settings > Risk Engine
    normalized_value: float | None  # 0..1, None when there isn't enough data yet
    contribution: float  # this factor's share of the 0..100 score
    available: bool


class RiskScoreOut(BaseModel):
    """The current deterministic risk score, per D008: same ingested data +
    same Settings always yields the same score/severity/breakdown."""

    score: float  # 0..100
    severity: str  # LOW | MODERATE | HIGH | CRITICAL
    factors: list[RiskFactorOut]
    factors_available: int
    factors_total: int
    computed_at: datetime
    # Session 018: False only when a non-demo city (no live connector) was
    # requested via ?city_id= — see app/services/city_context.py. Always
    # True for the pre-existing single-city behavior.
    data_available: bool = True
    planned_data_source: str | None = None


class WarningOut(BaseModel):
    id: uuid.UUID
    severity: str
    status: str
    risk_score: float
    factors: dict
    message: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    created_at: datetime
    updated_at: datetime
