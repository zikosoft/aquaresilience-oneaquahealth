"""P2 — deterministic risk score + early warnings API.

`GET /risk/current` both computes the current score (pure function of
ingested data + Settings, per D008) and idempotently evaluates the warning
lifecycle from it. Doing this on a GET is deliberate for demo reliability:
the result is identical whether it runs here, on the next scheduler tick
(`app.core.scheduler`), or both — the whole point of a deterministic engine
is that re-evaluating never changes the outcome for unchanged data, so this
stays safe to call as often as the Command Center/Alerts pages want.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.models.risk import Warning, WarningStatus
from app.models.user import User
from app.schemas.risk import RiskFactorOut, RiskScoreOut, RiskTrajectoryOut, TrajectoryPointOut, WarningOut
from app.services.city_context import get_primary_city_id, resolve_city
from app.services.risk_engine import compute_risk, compute_risk_trajectory, evaluate_and_persist_warnings

router = APIRouter()


def _warning_out(w: Warning) -> WarningOut:
    return WarningOut(
        id=w.id,
        severity=w.severity,
        status=w.status,
        risk_score=w.risk_score,
        factors=w.factors,
        message=w.message,
        triggered_at=w.triggered_at,
        acknowledged_at=w.acknowledged_at,
        acknowledged_by=w.acknowledged_by.full_name if w.acknowledged_by else None,
        resolved_at=w.resolved_at,
        resolved_by=w.resolved_by.full_name if w.resolved_by else None,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


@router.get("/current", response_model=RiskScoreOut)
def get_current_risk(
    city_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("DASHBOARD", "VIEW")),
) -> RiskScoreOut:
    city, has_data = resolve_city(db, city_id)
    if not has_data:
        return RiskScoreOut(
            score=0.0,
            severity="LOW",
            factors=[],
            factors_available=0,
            factors_total=4,
            computed_at=datetime.now(timezone.utc),
            data_available=False,
            planned_data_source=city.planned_data_source if city else None,
        )
    result = compute_risk(db, city_id=city.id if city else None)
    # Early Warnings has no per-city column yet (see get_primary_city_id's
    # docstring) — it stays keyed to Toulouse specifically regardless of
    # which city is being previewed, so switching the header to e.g. Vienna
    # can never overwrite/flap the one shared Warning row with Vienna's
    # score. A future per-city Warning redesign would remove this guard.
    if city is None or city.id == get_primary_city_id(db):
        evaluate_and_persist_warnings(db, result)
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


@router.get("/trajectory", response_model=RiskTrajectoryOut)
def get_risk_trajectory(
    city_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("DASHBOARD", "VIEW")),
) -> RiskTrajectoryOut:
    """P5 — WOW: Predictive Risk Trajectory. Read-only, deterministic,
    idempotent — safe to poll like `/risk/current`. Never touches the
    Warning table (that stays `evaluate_and_persist_warnings`'s job on the
    real, non-projected score)."""
    city, has_data = resolve_city(db, city_id)
    now = datetime.now(timezone.utc)
    if not has_data:
        return RiskTrajectoryOut(
            current_score=0.0,
            current_severity="LOW",
            points=[],
            trend_rate_mm_per_hour=None,
            basis="insufficient_data",
            computed_at=now,
            data_available=False,
            planned_data_source=city.planned_data_source if city else None,
        )
    trajectory = compute_risk_trajectory(db, now, city_id=city.id if city else None)
    return RiskTrajectoryOut(
        current_score=trajectory.current.score,
        current_severity=trajectory.current.severity,
        points=[
            TrajectoryPointOut(
                hours_ahead=p.hours_ahead,
                projected_at=p.projected_at,
                score=p.score,
                severity=p.severity,
                projected_water_level_mm=p.projected_water_level_mm,
            )
            for p in trajectory.points
        ],
        trend_rate_mm_per_hour=trajectory.trend_rate_mm_per_hour,
        basis=trajectory.basis,
        computed_at=trajectory.current.computed_at,
    )


@router.get("/warnings", response_model=list[WarningOut])
def list_warnings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ALERTS", "VIEW")),
) -> list[WarningOut]:
    rows = db.execute(select(Warning).order_by(Warning.triggered_at.desc())).scalars().all()
    return [_warning_out(w) for w in rows]


@router.post("/warnings/{warning_id}/acknowledge", response_model=WarningOut)
def acknowledge_warning(
    warning_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ALERTS", "EDIT")),
) -> WarningOut:
    warning = db.get(Warning, warning_id)
    if warning is None:
        raise NotFoundError(message="Warning not found")
    if warning.status != WarningStatus.ACTIVE.value:
        raise ConflictError(message=f"Warning is '{warning.status}', not ACTIVE")
    warning.status = WarningStatus.ACKNOWLEDGED.value
    warning.acknowledged_at = datetime.now(timezone.utc)
    warning.acknowledged_by_id = current_user.id
    db.commit()
    db.refresh(warning)
    return _warning_out(warning)


@router.post("/warnings/{warning_id}/resolve", response_model=WarningOut)
def resolve_warning(
    warning_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ALERTS", "EXECUTE")),
) -> WarningOut:
    warning = db.get(Warning, warning_id)
    if warning is None:
        raise NotFoundError(message="Warning not found")
    if warning.status == WarningStatus.RESOLVED.value:
        raise ConflictError(message="Warning is already RESOLVED")
    warning.status = WarningStatus.RESOLVED.value
    warning.resolved_at = datetime.now(timezone.utc)
    warning.resolved_by_id = current_user.id
    db.commit()
    db.refresh(warning)
    return _warning_out(warning)
