"""P4 — Scenario Simulator (Master Spec §20), the project's signature
differentiation feature.

Two independent halves, matching "the simulation calculation is
deterministic, AI explains the result":

1. `simulate_scenario` — ALWAYS deterministic, ALWAYS succeeds from stored
   data. Reuses `risk_engine.compute_risk`/`compute_projected_risk` (the
   exact same normalizers and combination logic the real, non-hypothetical
   risk score is built from — never a second, divergent computation path)
   to produce a Current vs. Projected pair, plus a non-persisting preview
   of what a Warning would look like at the projected severity. Nothing
   here ever calls an AI provider or touches the real `Warning` table.
2. `explain_scenario` — optional, best-effort. Turns the same
   deterministic result into a prompt for the configured AI provider and
   asks it to explain the projected change and suggest resilience actions.
   Mirrors `intelligence_service.generate_situation_brief`'s failure
   handling exactly: never raises, every failure path (not configured,
   cooldown, network/auth error, malformed/invalid JSON) is caught and
   returned as `ok=False` with a message — the caller (the API layer) must
   still return the full deterministic result either way. This is what
   guarantees "AI outage leaves core platform operational" extends to the
   Scenario Simulator too, not just the P3 Situation Brief.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.environmental import Measurement, MeasurementVariable
from app.models.settings import AIProviderConfig
from app.services import intelligence_service
from app.services.ai_provider_service import AIProviderError, get_or_create_ai_config, get_provider
from app.services.risk_engine import (
    RiskResult,
    scope_measurements_to_city,
    compute_projected_risk,
    compute_risk,
    describe_warning_outcome,
)

MAX_RECOMMENDATIONS = 5


@dataclass
class ScenarioResult:
    current: RiskResult
    projected: RiskResult
    rainfall_adjustment_pct: float
    river_level_adjustment_pct: float
    water_level_current: float | None
    water_level_projected: float | None
    precipitation_current: float | None
    precipitation_projected: float | None
    projected_warning: dict


@dataclass
class ScenarioExplanationResult:
    ok: bool
    message: str
    explanation: str | None = None
    resilience_recommendations: list[str] = field(default_factory=list)
    confidence: float | None = None


def _latest_water_level_mm(db: Session, city_id: uuid.UUID | None = None) -> float | None:
    query = (
        select(Measurement.value)
        .where(Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value)
        .order_by(Measurement.observed_at.desc())
        .limit(1)
    )
    return db.execute(scope_measurements_to_city(query, city_id)).scalar_one_or_none()


def _precipitation_24h_total_mm(db: Session, now: datetime, city_id: uuid.UUID | None = None) -> float | None:
    since = now - timedelta(hours=24)
    query = select(func.sum(Measurement.value)).where(
        Measurement.variable == MeasurementVariable.PRECIPITATION_MM.value,
        Measurement.observed_at >= since,
    )
    total = db.execute(scope_measurements_to_city(query, city_id)).scalar_one_or_none()
    return round(total, 1) if total is not None else None


def simulate_scenario(
    db: Session,
    rainfall_adjustment_pct: float,
    river_level_adjustment_pct: float,
    now: datetime | None = None,
    city_id: uuid.UUID | None = None,
) -> ScenarioResult:
    """Pure, deterministic, synchronous — no network call, no AI, safe to
    call as often as the UI wants (same reliability property as
    `GET /risk/current`).

    Session 020 fix: `city_id` (default None, unchanged global-scan
    behavior) scopes both the risk computation and this module's own
    water-level/precipitation readouts to one city — see
    `app.services.risk_engine.scope_measurements_to_city` for why this matters now
    that more than one city has real ingested measurements."""
    now = now or datetime.now(timezone.utc)
    current = compute_risk(db, now, city_id=city_id)
    projected = compute_projected_risk(
        db, rainfall_adjustment_pct, river_level_adjustment_pct, now, city_id=city_id
    )

    water_level = _latest_water_level_mm(db, city_id)
    precipitation = _precipitation_24h_total_mm(db, now, city_id)
    river_multiplier = 1.0 + (river_level_adjustment_pct / 100.0)
    rainfall_multiplier = 1.0 + (rainfall_adjustment_pct / 100.0)

    return ScenarioResult(
        current=current,
        projected=projected,
        rainfall_adjustment_pct=rainfall_adjustment_pct,
        river_level_adjustment_pct=river_level_adjustment_pct,
        water_level_current=water_level,
        water_level_projected=(
            round(max(0.0, water_level * river_multiplier), 1) if water_level is not None else None
        ),
        precipitation_current=precipitation,
        precipitation_projected=(
            round(max(0.0, precipitation * rainfall_multiplier), 1) if precipitation is not None else None
        ),
        projected_warning=describe_warning_outcome(projected),
    )


def _risk_summary(result: RiskResult) -> dict:
    return {
        "score": result.score,
        "severity": result.severity,
        "factors": [
            {"label": f.label, "contribution": f.contribution, "available": f.available} for f in result.factors
        ],
    }


SCENARIO_PROMPT_TEMPLATE = """You are the AI Resilience Intelligence layer of AquaResilience, a flood-resilience monitoring platform for Toulouse Métropole. A user is exploring a hypothetical "what if" scenario in the Scenario Simulator. Both risk scores below were already computed deterministically — you explain the change between them, you never recompute, override or contradict either number.

CURRENT (real, observed conditions):
{current_json}

SCENARIO ADJUSTMENTS APPLIED:
- Rainfall: {rainfall_pct:+.0f}%
- River level: {river_pct:+.0f}%

PROJECTED (deterministic outcome of applying those adjustments):
{projected_json}

Based ONLY on this data, respond with a single JSON object with EXACTLY these fields and no others:
{{
  "explanation": a concise 2-4 sentence plain-language explanation of why the risk would change from the current to the projected situation, naming the leading driving factor(s),
  "resilience_recommendations": an array of up to {max_items} short, concrete, actionable resilience recommendations for local operators to prepare for this projected scenario,
  "confidence": a number between 0 and 1 reflecting how much underlying data supports this explanation
}}

{language_instruction}
Respond with ONLY the JSON object — no markdown code fences, no extra commentary before or after it."""


def build_scenario_prompt(scenario: ScenarioResult, language: str) -> str:
    return SCENARIO_PROMPT_TEMPLATE.format(
        current_json=json.dumps(_risk_summary(scenario.current), indent=2),
        projected_json=json.dumps(_risk_summary(scenario.projected), indent=2),
        rainfall_pct=scenario.rainfall_adjustment_pct,
        river_pct=scenario.river_level_adjustment_pct,
        max_items=MAX_RECOMMENDATIONS,
        language_instruction=intelligence_service.LANGUAGE_INSTRUCTIONS.get(
            language, intelligence_service.LANGUAGE_INSTRUCTIONS[intelligence_service.DEFAULT_LANGUAGE]
        ),
    )


class _RawScenarioExplanation(BaseModel):
    """Same "validate before storage/display" discipline as P3's
    `_RawBriefPayload` — a malformed/out-of-range response is treated as a
    failed attempt, never partially trusted."""

    explanation: str = Field(min_length=1, max_length=2000)
    resilience_recommendations: list[str] = Field(max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)


def can_run_scenario_explanation(config: AIProviderConfig, now: datetime) -> tuple[bool, str]:
    if not config.is_configured:
        return False, "No AI provider is configured yet."
    if config.last_scenario_explanation_at is not None:
        elapsed = (now - config.last_scenario_explanation_at).total_seconds()
        if elapsed < config.cooldown_seconds:
            remaining = int(config.cooldown_seconds - elapsed)
            return False, f"Please wait {remaining}s before requesting another scenario explanation (cooldown)."
    return True, ""


async def explain_scenario(
    db: Session, scenario: ScenarioResult, language: str | None = None
) -> ScenarioExplanationResult:
    """Never raises. The caller must always have `scenario` (the
    deterministic result) ready to return regardless of what happens here —
    this function only ever adds an optional explanation on top."""
    config = get_or_create_ai_config(db)
    now = datetime.now(timezone.utc)
    language = (
        language
        if language in intelligence_service.LANGUAGE_INSTRUCTIONS
        else intelligence_service.DEFAULT_LANGUAGE
    )

    ok, reason = can_run_scenario_explanation(config, now)
    if not ok:
        return ScenarioExplanationResult(ok=False, message=reason)

    api_key = decrypt_secret(config.encrypted_api_key) if config.encrypted_api_key else None
    if api_key is None:
        return ScenarioExplanationResult(ok=False, message="Stored API key could not be decrypted.")

    prompt = build_scenario_prompt(scenario, language)
    provider = get_provider(config.provider, api_key=api_key, model=config.model)

    # Recorded before the attempt, success or failure alike — same rationale
    # as `intelligence_service`'s `last_analysis_attempt_at`: a broken key
    # gets retried at most once per cooldown window, not hammered on every
    # click of "Run Simulation".
    config.last_scenario_explanation_at = now

    try:
        raw_text = await provider.generate_json(prompt, config.max_output_tokens)
    except AIProviderError as exc:
        db.commit()
        return ScenarioExplanationResult(ok=False, message=str(exc)[:500])
    except Exception as exc:  # noqa: BLE001 — never let an unexpected provider bug escape
        db.commit()
        return ScenarioExplanationResult(ok=False, message=f"Unexpected error calling AI provider: {exc}"[:500])

    parsed_json = intelligence_service._extract_json(raw_text)
    if parsed_json is None:
        db.commit()
        return ScenarioExplanationResult(ok=False, message="AI response was not valid JSON.")

    try:
        payload = _RawScenarioExplanation.model_validate(parsed_json)
    except ValidationError as exc:
        db.commit()
        return ScenarioExplanationResult(
            ok=False, message=f"AI response failed schema validation: {exc.error_count()} error(s)."
        )

    db.commit()
    return ScenarioExplanationResult(
        ok=True,
        message="Scenario explanation generated.",
        explanation=payload.explanation,
        resilience_recommendations=payload.resilience_recommendations[:MAX_RECOMMENDATIONS],
        confidence=payload.confidence,
    )
