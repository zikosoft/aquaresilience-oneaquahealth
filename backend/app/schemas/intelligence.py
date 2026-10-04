"""P3 — AI Resilience Intelligence: Situation Brief + shared job status."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SituationBriefOut(BaseModel):
    id: uuid.UUID
    generated_at: datetime
    city_id: uuid.UUID | None = None
    language: str
    triggered_by: str
    situation: str
    summary: str
    drivers: list[str]
    zones_to_watch: list[str]
    recommendations: list[str]
    confidence: float
    limitations: list[str]
    risk_score_snapshot: float
    risk_severity_snapshot: str
    provider: str
    model: str

    model_config = {"from_attributes": True}


class AIIntelligenceStatusOut(BaseModel):
    is_configured: bool
    scheduled_analysis_interval_minutes: int
    daily_request_ceiling: int
    requests_today: int
    cooldown_seconds: int
    event_triggered_enabled: bool
    last_analysis_at: datetime | None
    next_analysis_at: datetime | None
    last_analysis_error: str | None


class TriggerAnalysisRequest(BaseModel):
    language: str | None = Field(default=None, pattern="^(en|fr|es|pt|no|el|de|it|nl)$")
    city_id: uuid.UUID | None = None


class TriggerAnalysisResult(BaseModel):
    ok: bool
    message: str
    brief: SituationBriefOut | None = None
