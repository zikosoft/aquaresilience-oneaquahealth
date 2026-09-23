"""P2 — deterministic Risk Engine.

Per D008 (locked decision) and Stop Rule #7: the risk score is a pure
function of already-ingested measurements plus the Settings > Risk Engine
configuration (weights + severity thresholds, seeded since P0). Same stored
data + same Settings always yields the same score, severity and per-factor
breakdown — AI is never a dependency for this computation; it may only
*explain* the result in P3.

Four factors, each normalized to 0..1, combined via the configured weights
into a single 0..100 score:

- rainfall: 24h cumulative precipitation vs. a documented 40mm/24h reference.
- hydrology: current Garonne water level vs. the station's own observed
  historical min/max range (relative/statistical fallback — see note below).
- environmental: soil moisture ratio, already expressed 0..1 by Open-Meteo.
- trend: rate of rise of the water level over the trailing 6h vs. a
  documented 50mm/h reference (a falling/flat level contributes 0, never
  negative risk).

Official Vigicrues numeric flood thresholds for the Garonne @ Toulouse
station (O200004001) could not be retrieved during development — the
station page and the Hub'Eau v2 threshold endpoints were unreachable from
this environment (robots.txt disallow / timeout / 404). Until official
numbers are available, the hydrology and rainfall reference constants below
are documented, adjustable fallbacks — not sourced flood-plan values. They
live as named constants specifically so they are easy to replace with
official numbers later without touching the combination logic.

A factor with insufficient underlying data (fresh install, no measurements
yet, a flat historical range, too few trend points, ...) is marked
unavailable and contributes nothing; the remaining available factors' weights
are renormalized proportionally so the score always stays a well-defined
weighted average instead of silently under-counting to zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.environmental import Measurement, MeasurementVariable
from app.models.risk import Warning, WarningStatus
from app.models.settings import AppSetting

# --- Documented fallback reference constants (see module docstring) ---
RAINFALL_REFERENCE_MM_24H = 40.0
TREND_REFERENCE_MM_PER_HOUR = 50.0
TREND_WINDOW_HOURS = 6
HYDROLOGY_LOOKBACK_DAYS = 90

DEFAULT_RISK_ENGINE_SETTINGS = {
    "weights": {"rainfall": 0.3, "hydrology": 0.3, "environmental": 0.2, "trend": 0.2},
    "thresholds": {"low": 25, "moderate": 50, "high": 75},
}

FACTOR_LABELS = {
    "rainfall": "Rainfall (24h)",
    "hydrology": "River level",
    "environmental": "Soil moisture",
    "trend": "Water level trend",
}

FACTOR_ORDER = ("rainfall", "hydrology", "environmental", "trend")

# A warning is (re)raised/kept open at MODERATE severity and above.
OPEN_SEVERITIES = {"MODERATE", "HIGH", "CRITICAL"}


@dataclass
class RiskFactor:
    key: str
    label: str
    weight: float
    normalized_value: float | None
    available: bool
    contribution: float = 0.0


@dataclass
class RiskResult:
    score: float
    severity: str
    factors: list[RiskFactor]
    factors_available: int
    factors_total: int
    computed_at: datetime


def _get_risk_engine_settings(db: Session) -> dict:
    row = db.execute(select(AppSetting).where(AppSetting.key == "risk_engine")).scalar_one_or_none()
    if row is None or not row.value:
        return DEFAULT_RISK_ENGINE_SETTINGS
    value = row.value
    weights = {**DEFAULT_RISK_ENGINE_SETTINGS["weights"], **(value.get("weights") or {})}
    thresholds = {**DEFAULT_RISK_ENGINE_SETTINGS["thresholds"], **(value.get("thresholds") or {})}
    return {"weights": weights, "thresholds": thresholds}


def _normalize_rainfall(db: Session, now: datetime) -> float | None:
    since = now - timedelta(hours=24)
    total = db.execute(
        select(func.sum(Measurement.value)).where(
            Measurement.variable == MeasurementVariable.PRECIPITATION_MM.value,
            Measurement.observed_at >= since,
        )
    ).scalar_one_or_none()
    if total is None:
        return None
    return max(0.0, min(total / RAINFALL_REFERENCE_MM_24H, 1.0))


def _normalize_hydrology(db: Session, now: datetime) -> float | None:
    latest = db.execute(
        select(Measurement.value)
        .where(Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value)
        .order_by(Measurement.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return None
    since = now - timedelta(days=HYDROLOGY_LOOKBACK_DAYS)
    lo, hi = db.execute(
        select(func.min(Measurement.value), func.max(Measurement.value)).where(
            Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value,
            Measurement.observed_at >= since,
        )
    ).one()
    if lo is None or hi is None or hi <= lo:
        # Flat/degenerate range (e.g. a single reading so far): not enough
        # signal yet to place the current level on a relative scale.
        return None
    return max(0.0, min((latest - lo) / (hi - lo), 1.0))


def _normalize_environmental(db: Session) -> float | None:
    latest = db.execute(
        select(Measurement.value)
        .where(Measurement.variable == MeasurementVariable.SOIL_MOISTURE_RATIO.value)
        .order_by(Measurement.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return None
    return max(0.0, min(latest, 1.0))


def _normalize_trend(db: Session, now: datetime) -> float | None:
    since = now - timedelta(hours=TREND_WINDOW_HOURS)
    rows = db.execute(
        select(Measurement.value, Measurement.observed_at)
        .where(
            Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value,
            Measurement.observed_at >= since,
        )
        .order_by(Measurement.observed_at)
    ).all()
    if len(rows) < 2:
        return None
    first_value, first_ts = rows[0]
    last_value, last_ts = rows[-1]
    hours_elapsed = (last_ts - first_ts).total_seconds() / 3600.0
    if hours_elapsed <= 0:
        return None
    rate = (last_value - first_value) / hours_elapsed
    return max(0.0, min(rate / TREND_REFERENCE_MM_PER_HOUR, 1.0))


def _severity_for_score(score: float, thresholds: dict) -> str:
    if score >= thresholds["high"]:
        return "CRITICAL"
    if score >= thresholds["moderate"]:
        return "HIGH"
    if score >= thresholds["low"]:
        return "MODERATE"
    return "LOW"


def compute_risk(db: Session, now: datetime | None = None) -> RiskResult:
    """Deterministic: reads only stored measurements + Settings, no
    randomness, no external calls, no AI. Same DB state -> same result."""
    now = now or datetime.now(timezone.utc)
    config = _get_risk_engine_settings(db)
    weights = config["weights"]
    thresholds = config["thresholds"]

    raw_values: dict[str, float | None] = {
        "rainfall": _normalize_rainfall(db, now),
        "hydrology": _normalize_hydrology(db, now),
        "environmental": _normalize_environmental(db),
        "trend": _normalize_trend(db, now),
    }

    available_keys = [k for k in FACTOR_ORDER if raw_values[k] is not None]
    available_weight_total = sum(weights.get(k, 0.0) for k in available_keys)

    factors: list[RiskFactor] = []
    score = 0.0
    for key in FACTOR_ORDER:
        value = raw_values[key]
        weight = weights.get(key, 0.0)
        available = value is not None
        contribution = 0.0
        if available and available_weight_total > 0:
            effective_weight = weight / available_weight_total
            contribution = value * effective_weight * 100.0
            score += contribution
        factors.append(
            RiskFactor(
                key=key,
                label=FACTOR_LABELS[key],
                weight=weight,
                normalized_value=value,
                available=available,
                contribution=round(contribution, 1),
            )
        )

    score = round(min(max(score, 0.0), 100.0), 1)
    severity = _severity_for_score(score, thresholds)

    return RiskResult(
        score=score,
        severity=severity,
        factors=factors,
        factors_available=len(available_keys),
        factors_total=len(FACTOR_ORDER),
        computed_at=now,
    )


def _factors_payload(result: RiskResult) -> dict:
    return {
        f.key: {
            "label": f.label,
            "weight": f.weight,
            "normalized_value": f.normalized_value,
            "contribution": f.contribution,
            "available": f.available,
        }
        for f in result.factors
    }


def _build_message(result: RiskResult) -> str:
    leading = max(result.factors, key=lambda f: f.contribution)
    return f"Risk score {result.score}/100 ({result.severity}) — leading factor: {leading.label}."


def evaluate_and_persist_warnings(db: Session, result: RiskResult) -> Warning | None:
    """Deterministic warning lifecycle, evaluated alongside `compute_risk`.

    - Creates a new ACTIVE warning the first time the score reaches
      MODERATE+ while none is currently open.
    - Updates an already-open warning's score/severity/factors in place on
      every re-evaluation (never creates a duplicate), without disturbing an
      operator's own ACKNOWLEDGED status.
    - Auto-resolves the open warning once the score drops back to LOW.

    Returns the currently open warning (ACTIVE or ACKNOWLEDGED) after this
    evaluation, or None if there isn't one.
    """
    open_warning = db.execute(
        select(Warning)
        .where(Warning.status.in_([WarningStatus.ACTIVE.value, WarningStatus.ACKNOWLEDGED.value]))
        .order_by(Warning.triggered_at.desc())
    ).scalars().first()

    if result.severity in OPEN_SEVERITIES:
        if open_warning is None:
            open_warning = Warning(
                severity=result.severity,
                status=WarningStatus.ACTIVE.value,
                risk_score=result.score,
                factors=_factors_payload(result),
                message=_build_message(result),
                triggered_at=result.computed_at,
            )
            db.add(open_warning)
        else:
            open_warning.severity = result.severity
            open_warning.risk_score = result.score
            open_warning.factors = _factors_payload(result)
            open_warning.message = _build_message(result)
        db.commit()
        db.refresh(open_warning)
        return open_warning

    if open_warning is not None:
        open_warning.status = WarningStatus.RESOLVED.value
        open_warning.resolved_at = result.computed_at
        db.commit()
    return None
