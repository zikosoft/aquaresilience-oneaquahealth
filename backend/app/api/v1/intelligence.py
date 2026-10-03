"""P3 — AI Resilience Intelligence API.

`GET /intelligence/brief` and `GET /intelligence/status` are gated on the
`AI_INTELLIGENCE` module (not `SETTINGS`), so Viewer/Operator can see the
shared brief without needing Settings access — same separation already used
for `MAP:VIEW` vs `SETTINGS:VIEW` on the map config (P2.1).

Neither GET endpoint ever calls the AI provider — they only read what the
scheduler (or a prior manual trigger) already produced, satisfying the P3
gate "no unnecessary LLM call on dashboard load". Only `POST /analyze`
calls out, and it is rate-limited by `can_run_manual_analysis` (cooldown +
daily ceiling) independently of the scheduler's own interval gate.

Session 022 (user request): `city_id` on `GET /brief` and `POST /analyze`
lets the brief follow the viewer's selected city instead of always being
about Toulouse — see `app.services.intelligence_service.
generate_situation_brief`. `resolve_city` degrades an unrecognized/stale id
the same way every other city-scoped endpoint does; omitting it keeps the
original default (the primary city).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.intelligence import SituationBrief
from app.models.user import User
from app.schemas.intelligence import (
    AIIntelligenceStatusOut,
    SituationBriefOut,
    TriggerAnalysisRequest,
    TriggerAnalysisResult,
)
from app.services.ai_provider_service import get_or_create_ai_config
from app.services.city_context import get_primary_city_id, resolve_city
from app.services.intelligence_service import can_run_manual_analysis, generate_situation_brief

router = APIRouter()


@router.get("/brief", response_model=SituationBriefOut | None)
def get_latest_brief(
    city_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("AI_INTELLIGENCE", "VIEW")),
) -> SituationBriefOut | None:
    # resolve_city degrades both "omitted" and "unrecognized/stale" the same
    # way (city=None) — either way, fall back to the primary city rather
    # than an ambiguous "most recent brief across every city" scan.
    city, _has_data = resolve_city(db, city_id)
    effective_city_id = city.id if city is not None else get_primary_city_id(db)
    query = select(SituationBrief).order_by(SituationBrief.generated_at.desc()).limit(1)
    if effective_city_id is not None:
        query = query.where(SituationBrief.city_id == effective_city_id)
    brief = db.execute(query).scalar_one_or_none()
    return brief


@router.get("/status", response_model=AIIntelligenceStatusOut)
def get_intelligence_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("AI_INTELLIGENCE", "VIEW")),
) -> AIIntelligenceStatusOut:
    config = get_or_create_ai_config(db)
    next_analysis_at: datetime | None = None
    if config.is_configured and config.last_analysis_attempt_at is not None:
        next_analysis_at = config.last_analysis_attempt_at + timedelta(
            minutes=config.scheduled_analysis_interval_minutes
        )
    today = datetime.now(timezone.utc).date()
    requests_today = config.requests_today if config.requests_today_date == today else 0
    return AIIntelligenceStatusOut(
        is_configured=config.is_configured,
        scheduled_analysis_interval_minutes=config.scheduled_analysis_interval_minutes,
        daily_request_ceiling=config.daily_request_ceiling,
        requests_today=requests_today,
        cooldown_seconds=config.cooldown_seconds,
        event_triggered_enabled=config.event_triggered_enabled,
        last_analysis_at=config.last_analysis_attempt_at,
        next_analysis_at=next_analysis_at,
        last_analysis_error=config.last_analysis_error,
    )


@router.post("/analyze", response_model=TriggerAnalysisResult)
async def trigger_analysis(
    payload: TriggerAnalysisRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("AI_INTELLIGENCE", "EXECUTE")),
) -> TriggerAnalysisResult:
    config = get_or_create_ai_config(db)
    now = datetime.now(timezone.utc)
    ok, reason = can_run_manual_analysis(config, now)
    if not ok:
        return TriggerAnalysisResult(ok=False, message=reason)

    city, _has_data = resolve_city(db, payload.city_id)
    effective_city_id = city.id if city is not None else get_primary_city_id(db)
    result = await generate_situation_brief(
        db, language=payload.language, triggered_by="manual", city_id=effective_city_id
    )
    return TriggerAnalysisResult(ok=result.ok, message=result.message, brief=result.brief)
