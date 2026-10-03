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
    # Defaults to the deployment's default locale when omitted (see
    # app.api.v1.intelligence) — a scheduled/background run has no "current
    # user" to take a UI language from, but a manual click does, so the
    # frontend passes its own active locale here (Master Spec §19: "active
    # UI language passed to the AI").
    # Session 019: widened to all 9 UI languages — was still en|fr|es only
    # from before session 018 added pt/no/el/de/it/nl, which meant a manual
    # analysis request from one of those 6 UI languages was rejected (422)
    # rather than degrading gracefully. See intelligence_service.py's
    # LANGUAGE_INSTRUCTIONS for the matching fix.
    language: str | None = Field(default=None, pattern="^(en|fr|es|pt|no|el|de|it|nl)$")
    # Session 022 (user request): which city to analyze — defaults to the
    # platform's primary city (Toulouse) server-side when omitted, same as
    # before this field existed. The frontend always sends the viewer's
    # currently selected city explicitly.
    city_id: uuid.UUID | None = None


class TriggerAnalysisResult(BaseModel):
    ok: bool
    message: str
    brief: SituationBriefOut | None = None
