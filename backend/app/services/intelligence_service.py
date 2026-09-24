"""P3 — AI Resilience Intelligence pipeline (Master Spec §18-19).

OBSERVE -> CORRELATE -> INTERPRET -> EXPLAIN -> RECOMMEND:

1. OBSERVE/CORRELATE: `build_environmental_snapshot` assembles the current
   deterministic risk score + factor breakdown (P2, D008 — never
   recomputed or second-guessed by the AI), the open warning if any, and
   the latest key readings into one structured, JSON-serializable dict.
2. INTERPRET/EXPLAIN/RECOMMEND: `generate_situation_brief` turns that
   snapshot into a prompt, calls the configured provider, and validates the
   response against the exact schema from Master Spec §18 before it is ever
   stored or shown.

AI is an interpretive decision-support layer, never the environmental truth
engine (§18) — every number this pipeline puts in front of the AI already
came from the deterministic Risk Engine/ingested measurements; the AI only
explains and recommends, never (re)calculates risk. Every failure mode
(not configured, bad key, network error, malformed/invalid JSON) is caught
here and recorded, never raised — the calling scheduler tick and the manual
`/intelligence/analyze` endpoint both rely on this to guarantee "AI outage
leaves core platform operational" (§19 gate).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.environmental import DataSource, Measurement, MeasurementVariable, Station
from app.models.intelligence import SituationBrief
from app.models.settings import AIProviderConfig, AppSetting
from app.services.ai_provider_service import AIProviderError, get_or_create_ai_config, get_provider
from app.services.ingestion_service import compute_source_health
from app.services.risk_engine import compute_risk, evaluate_and_persist_warnings

LANGUAGE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "fr": "Réponds en français.",
    "es": "Responde en español.",
}
DEFAULT_LANGUAGE = "en"

MAX_LIST_ITEMS = 5
MAX_LIMITATIONS = 3
SITUATION_VALUES = ("low", "moderate", "high", "critical")

# Deterministic risk severity -> the vocabulary the AI's JSON `situation`
# field must use (Master Spec §18 example uses lowercase; the Risk Engine's
# own severity is uppercase — this is the one place the two vocabularies meet).
_SEVERITY_TO_SITUATION = {"LOW": "low", "MODERATE": "moderate", "HIGH": "high", "CRITICAL": "critical"}


@dataclass
class BriefGenerationResult:
    ok: bool
    message: str
    brief: SituationBrief | None = None


def get_default_language(db: Session) -> str:
    """The deployment's configured default UI locale (Settings > Languages),
    used for the shared scheduled brief — a background job has no "current
    user" to take an active UI language from (Master Spec §19's "active UI
    language passed to the AI" applies per-request on the manual endpoint,
    which lets a viewer's own active locale drive an on-demand refresh)."""
    row = db.execute(select(AppSetting).where(AppSetting.key == "languages")).scalar_one_or_none()
    if row is None or not row.value:
        return DEFAULT_LANGUAGE
    locale = row.value.get("default_locale")
    return locale if locale in LANGUAGE_INSTRUCTIONS else DEFAULT_LANGUAGE


def build_environmental_snapshot(db: Session, now: datetime) -> dict:
    """Structured, JSON-serializable snapshot of "what's happening right
    now" — the only input the AI ever sees. Every value here is read from
    already-ingested/-computed data, nothing is invented for the prompt."""
    risk = compute_risk(db, now)
    warning = evaluate_and_persist_warnings(db, risk)

    def _latest(variable: MeasurementVariable) -> dict | None:
        row = db.execute(
            select(Measurement)
            .where(Measurement.variable == variable.value)
            .order_by(Measurement.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {"value": row.value, "unit": row.unit, "observed_at": row.observed_at.isoformat()}

    since_24h = now - timedelta(hours=24)
    precip_24h = db.execute(
        select(func.sum(Measurement.value)).where(
            Measurement.variable == MeasurementVariable.PRECIPITATION_MM.value,
            Measurement.observed_at >= since_24h,
        )
    ).scalar_one_or_none()

    sources = db.execute(select(DataSource)).scalars().all()
    active_sources = sum(1 for s in sources if s.is_active)
    fresh_sources = sum(1 for s in sources if compute_source_health(s, now).value == "fresh")
    monitored_stations = db.execute(select(func.count(Station.id))).scalar_one()

    return {
        "computed_at": now.isoformat(),
        "risk": {
            "score": risk.score,
            "severity": risk.severity,
            "factors": [
                {
                    "key": f.key,
                    "label": f.label,
                    "weight": f.weight,
                    "normalized_value": f.normalized_value,
                    "contribution": f.contribution,
                    "available": f.available,
                }
                for f in risk.factors
            ],
        },
        "active_warning": (
            {"severity": warning.severity, "status": warning.status, "message": warning.message}
            if warning is not None
            else None
        ),
        "readings": {
            "water_level_mm": _latest(MeasurementVariable.WATER_LEVEL_MM),
            "precipitation_24h_total_mm": round(precip_24h, 1) if precip_24h is not None else None,
            "soil_moisture_ratio": _latest(MeasurementVariable.SOIL_MOISTURE_RATIO),
            "temperature_c": _latest(MeasurementVariable.TEMPERATURE_C),
        },
        "monitoring": {
            "monitored_stations": monitored_stations,
            "active_sources": active_sources,
            "fresh_sources": fresh_sources,
        },
    }, risk


PROMPT_TEMPLATE = """You are the AI Resilience Intelligence layer of AquaResilience, a flood-resilience monitoring platform for Toulouse Métropole. You are an interpretive decision-support layer, NOT the source of truth for risk — the numeric risk score below was already computed deterministically; never contradict it or invent a different number.

Current environmental snapshot (JSON):
{snapshot_json}

Based ONLY on this snapshot, respond with a single JSON object with EXACTLY these fields and no others:
{{
  "situation": one of "low", "moderate", "high", "critical" (must match the snapshot's risk.severity),
  "summary": a concise 1-3 sentence plain-language summary of the current situation,
  "drivers": an array of up to {max_items} short strings naming the factors driving this situation,
  "zones_to_watch": an array of up to {max_items} short strings naming areas/aspects to watch (if none are distinguishable from this single-station snapshot, return an empty array — do not invent specific place names not implied by the data),
  "recommendations": an array of up to {max_items} short, concrete, actionable recommendations for local operators,
  "confidence": a number between 0 and 1 reflecting how much underlying data supports this analysis,
  "limitations": an array of up to {max_limitations} short strings naming real limitations of this analysis (e.g. data gaps, factors unavailable)
}}

{language_instruction}
Respond with ONLY the JSON object — no markdown code fences, no extra commentary before or after it."""


def build_prompt(snapshot: dict, language: str) -> str:
    return PROMPT_TEMPLATE.format(
        snapshot_json=json.dumps(snapshot, indent=2),
        max_items=MAX_LIST_ITEMS,
        max_limitations=MAX_LIMITATIONS,
        language_instruction=LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS[DEFAULT_LANGUAGE]),
    )


class _RawBriefPayload(BaseModel):
    """Strict validation of the LLM's JSON output before it is ever stored
    or displayed (Master Spec §18: "Validate the response before
    storage/display"). Anything that fails this never reaches the DB."""

    situation: str = Field(pattern="^(low|moderate|high|critical)$")
    summary: str = Field(min_length=1, max_length=2000)
    drivers: list[str] = Field(max_length=20)
    zones_to_watch: list[str] = Field(max_length=20)
    recommendations: list[str] = Field(max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(max_length=20)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw_text: str) -> dict | None:
    """Tolerates markdown code fences / stray prose around the JSON object
    that some providers add despite being asked not to."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _reset_daily_counter_if_needed(config: AIProviderConfig, today: date) -> None:
    if config.requests_today_date != today:
        config.requests_today = 0
        config.requests_today_date = today


def should_run_scheduled_analysis(config: AIProviderConfig, now: datetime) -> bool:
    if not config.is_configured:
        return False
    today = now.date()
    effective_count = 0 if config.requests_today_date != today else config.requests_today
    if effective_count >= config.daily_request_ceiling:
        return False
    if config.last_analysis_attempt_at is None:
        return True
    elapsed_minutes = (now - config.last_analysis_attempt_at).total_seconds() / 60.0
    return elapsed_minutes >= config.scheduled_analysis_interval_minutes


# Session 017: the Settings > AI Provider "Event-triggered analysis" toggle
# has existed since P3 (stored on AIProviderConfig, shown in the UI) but
# nothing ever read it — flipping it changed nothing (user report). Wired
# here: an "event" is the risk crossing into HIGH/CRITICAL (not the lower
# MODERATE bar that merely opens a warning — that would fire far too often
# to be a meaningful "event"), gated by the exact same cooldown/daily
# ceiling as a human-requested manual refresh, so an event can never bypass
# the same budget a person is held to.
EVENT_TRIGGER_SEVERITIES = {"HIGH", "CRITICAL"}


def should_run_event_triggered_analysis(
    config: AIProviderConfig, warning_severity: str | None, now: datetime
) -> bool:
    if not config.event_triggered_enabled:
        return False
    if warning_severity not in EVENT_TRIGGER_SEVERITIES:
        return False
    ok, _reason = can_run_manual_analysis(config, now)
    return ok


def can_run_manual_analysis(config: AIProviderConfig, now: datetime) -> tuple[bool, str]:
    """Returns (ok, reason_if_not_ok). Manual/event-triggered refresh is
    gated by the cooldown (not the full scheduled interval — it's meant to
    allow a sooner, human-requested look) and the same daily ceiling."""
    if not config.is_configured:
        return False, "No AI provider is configured yet."
    today = now.date()
    effective_count = 0 if config.requests_today_date != today else config.requests_today
    if effective_count >= config.daily_request_ceiling:
        return False, "Today's AI analysis request limit has been reached."
    if config.last_analysis_attempt_at is not None:
        elapsed_seconds = (now - config.last_analysis_attempt_at).total_seconds()
        if elapsed_seconds < config.cooldown_seconds:
            remaining = int(config.cooldown_seconds - elapsed_seconds)
            return False, f"Please wait {remaining}s before requesting another analysis (cooldown)."
    return True, ""


async def generate_situation_brief(
    db: Session, language: str | None = None, triggered_by: str = "scheduled"
) -> BriefGenerationResult:
    """Never raises. Every failure path records `last_analysis_error` on the
    shared config and returns ok=False instead — callers (scheduler tick,
    manual endpoint) must never let this take down anything else."""
    config = get_or_create_ai_config(db)
    now = datetime.now(timezone.utc)
    language = language if language in LANGUAGE_INSTRUCTIONS else DEFAULT_LANGUAGE

    if not config.is_configured:
        return BriefGenerationResult(ok=False, message="No AI provider is configured yet.")

    api_key = decrypt_secret(config.encrypted_api_key) if config.encrypted_api_key else None
    if api_key is None:
        config.last_analysis_error = "Stored API key could not be decrypted."
        config.last_analysis_attempt_at = now
        db.commit()
        return BriefGenerationResult(ok=False, message=config.last_analysis_error)

    snapshot, risk = build_environmental_snapshot(db, now)
    prompt = build_prompt(snapshot, language)
    provider = get_provider(config.provider, api_key=api_key, model=config.model)

    # Every real outbound attempt counts against today's ceiling and resets
    # the scheduling/cooldown clock, success or failure alike (see
    # should_run_scheduled_analysis's docstring on why).
    _reset_daily_counter_if_needed(config, now.date())
    config.requests_today += 1
    config.last_analysis_attempt_at = now

    try:
        raw_text = await provider.generate_json(prompt, config.max_output_tokens)
    except AIProviderError as exc:
        config.last_analysis_error = str(exc)[:500]
        db.commit()
        return BriefGenerationResult(ok=False, message=config.last_analysis_error)
    except Exception as exc:  # noqa: BLE001 — never let an unexpected provider bug escape
        config.last_analysis_error = f"Unexpected error calling AI provider: {exc}"[:500]
        db.commit()
        return BriefGenerationResult(ok=False, message=config.last_analysis_error)

    parsed_json = _extract_json(raw_text)
    if parsed_json is None:
        config.last_analysis_error = "AI response was not valid JSON."
        db.commit()
        return BriefGenerationResult(ok=False, message=config.last_analysis_error)

    try:
        payload = _RawBriefPayload.model_validate(parsed_json)
    except ValidationError as exc:
        config.last_analysis_error = f"AI response failed schema validation: {exc.error_count()} error(s)."
        db.commit()
        return BriefGenerationResult(ok=False, message=config.last_analysis_error)

    brief = SituationBrief(
        generated_at=now,
        language=language,
        triggered_by=triggered_by,
        # Deliberately NOT payload.situation: the prompt asks the AI to
        # match the snapshot's risk.severity, but an LLM can still drift —
        # forcing it from the same deterministic mapping the prompt itself
        # was built from guarantees the badge shown next to the brief can
        # never contradict the Risk Engine's own number (Master Spec §18:
        # AI is interpretive, never the truth engine). `payload.situation`
        # is still schema-validated above so a malformed value fails loudly.
        situation=_SEVERITY_TO_SITUATION[risk.severity],
        summary=payload.summary,
        drivers=payload.drivers[:MAX_LIST_ITEMS],
        zones_to_watch=payload.zones_to_watch[:MAX_LIST_ITEMS],
        recommendations=payload.recommendations[:MAX_LIST_ITEMS],
        confidence=payload.confidence,
        limitations=payload.limitations[:MAX_LIMITATIONS],
        risk_score_snapshot=risk.score,
        risk_severity_snapshot=risk.severity,
        provider=config.provider,
        model=config.model,
    )
    db.add(brief)
    config.last_analysis_error = None
    db.commit()
    db.refresh(brief)
    return BriefGenerationResult(ok=True, message="Situation Brief generated.", brief=brief)
