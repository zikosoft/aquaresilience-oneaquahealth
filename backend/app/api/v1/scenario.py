"""P4 — Scenario Simulator API (Master Spec §20).

A single endpoint: the deterministic projection always succeeds from stored
data, and the optional AI explanation is layered on top without ever being
able to take the response down (see `scenario_service` module docstring).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.risk import RiskFactorOut, RiskScoreOut
from app.schemas.scenario import (
    ScenarioAIExplanationOut,
    ScenarioSimulateRequest,
    ScenarioSimulateResponse,
    ScenarioWarningPreviewOut,
)
from app.services.city_context import resolve_city
from app.services.risk_engine import RiskResult
from app.services.scenario_service import explain_scenario, simulate_scenario

router = APIRouter()


def _risk_score_out(result: RiskResult) -> RiskScoreOut:
    return RiskScoreOut(
        score=result.score,
        severity=result.severity,
        factors=[
            RiskFactorOut(
                key=f.key,
                label=f.label,
                weight=f.weight,
                normalized_value=f.normalized_value,
                contribution=f.contribution,
                available=f.available,
            )
            for f in result.factors
        ],
        factors_available=result.factors_available,
        factors_total=result.factors_total,
        computed_at=result.computed_at,
    )


@router.post("/simulate", response_model=ScenarioSimulateResponse)
async def simulate(
    payload: ScenarioSimulateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("SCENARIOS", "EXECUTE")),
) -> ScenarioSimulateResponse:
    city, has_data = resolve_city(db, payload.city_id)
    if not has_data:
        empty = RiskScoreOut(
            score=0.0,
            severity="LOW",
            factors=[],
            factors_available=0,
            factors_total=4,
            computed_at=datetime.now(timezone.utc),
            data_available=False,
            planned_data_source=city.planned_data_source if city else None,
        )
        return ScenarioSimulateResponse(
            current=empty,
            projected=empty,
            rainfall_adjustment_pct=payload.rainfall_adjustment_pct,
            river_level_adjustment_pct=payload.river_level_adjustment_pct,
            water_level_mm_current=None,
            water_level_mm_projected=None,
            precipitation_24h_mm_current=None,
            precipitation_24h_mm_projected=None,
            projected_warning=ScenarioWarningPreviewOut(would_trigger=False, severity=None, message=None),
            ai_explanation=None,
            ai_explanation_error=None,
        )

    scenario = simulate_scenario(
        db,
        payload.rainfall_adjustment_pct,
        payload.river_level_adjustment_pct,
        city_id=city.id if city else None,
    )

    ai_explanation: ScenarioAIExplanationOut | None = None
    ai_explanation_error: str | None = None
    if payload.include_ai_explanation:
        result = await explain_scenario(db, scenario, language=payload.language)
        if result.ok:
            ai_explanation = ScenarioAIExplanationOut(
                explanation=result.explanation or "",
                resilience_recommendations=result.resilience_recommendations,
                confidence=result.confidence if result.confidence is not None else 0.0,
            )
        else:
            ai_explanation_error = result.message

    return ScenarioSimulateResponse(
        current=_risk_score_out(scenario.current),
        projected=_risk_score_out(scenario.projected),
        rainfall_adjustment_pct=scenario.rainfall_adjustment_pct,
        river_level_adjustment_pct=scenario.river_level_adjustment_pct,
        water_level_mm_current=scenario.water_level_current,
        water_level_mm_projected=scenario.water_level_projected,
        precipitation_24h_mm_current=scenario.precipitation_current,
        precipitation_24h_mm_projected=scenario.precipitation_projected,
        projected_warning=ScenarioWarningPreviewOut(**scenario.projected_warning),
        ai_explanation=ai_explanation,
        ai_explanation_error=ai_explanation_error,
    )
