from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.risk import RiskScoreOut


class ScenarioSimulateRequest(BaseModel):
    rainfall_adjustment_pct: float = Field(0.0, ge=-100.0, le=300.0)
    river_level_adjustment_pct: float = Field(0.0, ge=-100.0, le=300.0)
    # Active UI language of the requesting viewer (same pattern as P3's
    # manual `/intelligence/analyze`) — used only for the optional AI
    # explanation; the deterministic projection itself has no language.
    language: str | None = Field(default=None, pattern="^(en|fr|es|pt|no|el|de|it|nl)$")
    # Lets the frontend re-run just the deterministic projection (e.g. while
    # a slider is being dragged) without spending an AI call every time —
    # only "Run Simulation" itself sends true.
    include_ai_explanation: bool = True
    city_id: uuid.UUID | None = None


class ScenarioWarningPreviewOut(BaseModel):
    would_trigger: bool
    severity: str | None
    message: str | None


class ScenarioAIExplanationOut(BaseModel):
    explanation: str
    resilience_recommendations: list[str]
    confidence: float


class ScenarioSimulateResponse(BaseModel):
    current: RiskScoreOut
    projected: RiskScoreOut
    rainfall_adjustment_pct: float
    river_level_adjustment_pct: float
    water_level_mm_current: float | None
    water_level_mm_projected: float | None
    precipitation_24h_mm_current: float | None
    precipitation_24h_mm_projected: float | None
    projected_warning: ScenarioWarningPreviewOut
    # Exactly one of these is populated: a null `ai_explanation` always
    # comes with a non-null `ai_explanation_error` explaining why (not
    # configured, cooldown, provider failure, ...) — the deterministic
    # fields above are always present either way.
    ai_explanation: ScenarioAIExplanationOut | None
    ai_explanation_error: str | None
