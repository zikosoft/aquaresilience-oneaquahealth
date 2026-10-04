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

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.environmental import DataSource, Measurement, MeasurementVariable, Station
from app.models.risk import Warning, WarningStatus
from app.models.settings import AppSetting


def scope_measurements_to_city(query: Select, city_id: uuid.UUID | None) -> Select:
    """Scope a Measurement query to one city's own stations.

    Without a filter, a scan blends every city's river levels/rainfall into
    one meaningless number once more than one city ingests real
    measurements. `city_id=None` (the default) keeps the global scan
    unchanged; passing it scopes the query through Station -> DataSource to
    that one city's own stations only."""
    if city_id is None:
        return query
    return (
        query.join(Station, Station.id == Measurement.station_id)
        .join(DataSource, DataSource.id == Station.data_source_id)
        .where(DataSource.city_id == city_id)
    )

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


def _normalize_rainfall(
    db: Session, now: datetime, multiplier: float = 1.0, city_id: uuid.UUID | None = None
) -> float | None:
    """`multiplier` defaults to 1.0 (unchanged, real-data behavior). P4's
    Scenario Simulator (`compute_projected_risk`) passes a
    `1 + rainfall_adjustment_pct/100` multiplier here to scale the actual
    observed 24h total by a hypothetical +X% — never a second, divergent
    computation path, just this same normalizer fed a scaled input."""
    since = now - timedelta(hours=24)
    query = select(func.sum(Measurement.value)).where(
        Measurement.variable == MeasurementVariable.PRECIPITATION_MM.value,
        Measurement.observed_at >= since,
    )
    total = db.execute(scope_measurements_to_city(query, city_id)).scalar_one_or_none()
    if total is None:
        return None
    adjusted = max(0.0, total * multiplier)
    return max(0.0, min(adjusted / RAINFALL_REFERENCE_MM_24H, 1.0))


def _latest_water_level_mm(db: Session, city_id: uuid.UUID | None = None) -> float | None:
    query = (
        select(Measurement.value)
        .where(Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value)
        .order_by(Measurement.observed_at.desc())
        .limit(1)
    )
    return db.execute(scope_measurements_to_city(query, city_id)).scalar_one_or_none()


def _normalize_hydrology(
    db: Session, now: datetime, multiplier: float = 1.0, city_id: uuid.UUID | None = None
) -> float | None:
    """See `_normalize_rainfall`'s docstring — same pattern, scaling the
    latest observed water level by a hypothetical river-level adjustment."""
    latest = _latest_water_level_mm(db, city_id)
    if latest is None:
        return None
    adjusted_latest = max(0.0, latest * multiplier)
    since = now - timedelta(days=HYDROLOGY_LOOKBACK_DAYS)
    query = select(func.min(Measurement.value), func.max(Measurement.value)).where(
        Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value,
        Measurement.observed_at >= since,
    )
    lo, hi = db.execute(scope_measurements_to_city(query, city_id)).one()
    if lo is None or hi is None or hi <= lo:
        # Flat/degenerate range (e.g. a single reading so far): not enough
        # signal yet to place the current level on a relative scale.
        return None
    return max(0.0, min((adjusted_latest - lo) / (hi - lo), 1.0))


def _normalize_environmental(db: Session, city_id: uuid.UUID | None = None) -> float | None:
    query = (
        select(Measurement.value)
        .where(Measurement.variable == MeasurementVariable.SOIL_MOISTURE_RATIO.value)
        .order_by(Measurement.observed_at.desc())
        .limit(1)
    )
    latest = db.execute(scope_measurements_to_city(query, city_id)).scalar_one_or_none()
    if latest is None:
        return None
    return max(0.0, min(latest, 1.0))


def _trend_window_rows(db: Session, now: datetime, city_id: uuid.UUID | None = None) -> list | None:
    """Shared trailing-`TREND_WINDOW_HOURS` water-level rows, used by both
    `_normalize_trend` (the real score's 0..1 trend factor) and
    `_trend_rate_mm_per_hour` (P5's raw mm/h rate — see below) so the two
    can never read a different window or drift apart."""
    since = now - timedelta(hours=TREND_WINDOW_HOURS)
    query = (
        select(Measurement.value, Measurement.observed_at)
        .where(
            Measurement.variable == MeasurementVariable.WATER_LEVEL_MM.value,
            Measurement.observed_at >= since,
        )
        .order_by(Measurement.observed_at)
    )
    rows = db.execute(scope_measurements_to_city(query, city_id)).all()
    return rows if len(rows) >= 2 else None


def _normalize_trend(
    db: Session, now: datetime, level_multiplier: float = 1.0, city_id: uuid.UUID | None = None
) -> float | None:
    """`level_multiplier` defaults to 1.0 (unchanged, real-data behavior).
    P4 passes the same river-level multiplier used by `_normalize_hydrology`
    here too, applied to the *most recent* reading only: the implied rate of
    rise is recomputed as if the water level ends up at that projected
    value by `last_ts`, rather than independently scaling the observed rate
    itself (which would wrongly make an already-falling trend fall faster
    under a "river level up" scenario)."""
    rows = _trend_window_rows(db, now, city_id)
    if rows is None:
        return None
    first_value, first_ts = rows[0]
    last_value, last_ts = rows[-1]
    adjusted_last_value = max(0.0, last_value * level_multiplier)
    hours_elapsed = (last_ts - first_ts).total_seconds() / 3600.0
    if hours_elapsed <= 0:
        return None
    rate = (adjusted_last_value - first_value) / hours_elapsed
    return max(0.0, min(rate / TREND_REFERENCE_MM_PER_HOUR, 1.0))


def _trend_rate_mm_per_hour(db: Session, now: datetime, city_id: uuid.UUID | None = None) -> float | None:
    """Raw (unnormalized, unclamped) mm/hour rate of rise over the same
    trailing window `_normalize_trend` uses — a real physical rate rather
    than a 0..1 score contribution. Used exclusively by
    `compute_risk_trajectory` (P5 — WOW: Predictive Risk Trajectory) to
    linearly extrapolate the water level forward; `_normalize_trend` still
    owns the real score's own factor value, untouched by this function."""
    rows = _trend_window_rows(db, now, city_id)
    if rows is None:
        return None
    first_value, first_ts = rows[0]
    last_value, last_ts = rows[-1]
    hours_elapsed = (last_ts - first_ts).total_seconds() / 3600.0
    if hours_elapsed <= 0:
        return None
    return (last_value - first_value) / hours_elapsed


def _severity_for_score(score: float, thresholds: dict) -> str:
    if score >= thresholds["high"]:
        return "CRITICAL"
    if score >= thresholds["moderate"]:
        return "HIGH"
    if score >= thresholds["low"]:
        return "MODERATE"
    return "LOW"


def _combine_factors(
    raw_values: dict[str, float | None], weights: dict, thresholds: dict, now: datetime
) -> RiskResult:
    """The single scoring/combination step shared by `compute_risk` (real
    ingested data) and `compute_projected_risk` (P4: hypothetical scenario
    inputs) — same weighted-average-with-renormalization logic either way,
    so a projection can never drift from how the real score is computed."""
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


def compute_risk(db: Session, now: datetime | None = None, city_id: uuid.UUID | None = None) -> RiskResult:
    """Deterministic: reads only stored measurements + Settings, no
    randomness, no external calls, no AI. Same DB state -> same result."""
    now = now or datetime.now(timezone.utc)
    config = _get_risk_engine_settings(db)
    weights = config["weights"]
    thresholds = config["thresholds"]

    raw_values: dict[str, float | None] = {
        "rainfall": _normalize_rainfall(db, now, city_id=city_id),
        "hydrology": _normalize_hydrology(db, now, city_id=city_id),
        "environmental": _normalize_environmental(db, city_id=city_id),
        "trend": _normalize_trend(db, now, city_id=city_id),
    }
    return _combine_factors(raw_values, weights, thresholds, now)


def compute_projected_risk(
    db: Session,
    rainfall_adjustment_pct: float,
    river_level_adjustment_pct: float,
    now: datetime | None = None,
    city_id: uuid.UUID | None = None,
) -> RiskResult:
    """P4 — Scenario Simulator (Master Spec §20). Deterministic projection:
    the rainfall/hydrology/trend factors are recomputed from the exact same
    normalizers `compute_risk` uses, fed the real observed data scaled by
    the requested percentage adjustments — never a separate model, never
    randomness, never an AI call. The environmental (soil moisture) factor
    is left as currently observed since it isn't one of the exposed
    scenario controls (Master Spec §20 only lists rainfall/river-level/
    optional temperature, and temperature isn't a Risk Engine factor)."""
    now = now or datetime.now(timezone.utc)
    config = _get_risk_engine_settings(db)
    weights = config["weights"]
    thresholds = config["thresholds"]

    rainfall_multiplier = 1.0 + (rainfall_adjustment_pct / 100.0)
    river_multiplier = 1.0 + (river_level_adjustment_pct / 100.0)

    raw_values: dict[str, float | None] = {
        "rainfall": _normalize_rainfall(db, now, multiplier=rainfall_multiplier, city_id=city_id),
        "hydrology": _normalize_hydrology(db, now, multiplier=river_multiplier, city_id=city_id),
        "environmental": _normalize_environmental(db, city_id=city_id),
        "trend": _normalize_trend(db, now, level_multiplier=river_multiplier, city_id=city_id),
    }
    return _combine_factors(raw_values, weights, thresholds, now)


TRAJECTORY_HORIZONS_HOURS: tuple[int, ...] = (1, 3, 6, 12)


@dataclass
class TrajectoryPoint:
    hours_ahead: int
    projected_at: datetime
    score: float
    severity: str
    projected_water_level_mm: float | None


@dataclass
class RiskTrajectory:
    current: RiskResult
    points: list[TrajectoryPoint]
    trend_rate_mm_per_hour: float | None
    basis: str  # "rising_trend" | "flat_or_falling" | "insufficient_data"


def compute_risk_trajectory(
    db: Session,
    now: datetime | None = None,
    horizons_hours: tuple[int, ...] = TRAJECTORY_HORIZONS_HOURS,
    city_id: uuid.UUID | None = None,
) -> RiskTrajectory:
    """P5 — Predictive Risk Trajectory (WOW feature; Track 6's "predictive
    dashboards" wording). Deterministic, and — per Stop Rule #7 — reuses the
    Risk Engine's own trend factor rather than building a second, separate
    forecasting model:

    1. Read the same trailing-`TREND_WINDOW_HOURS` rate of rise
       (`_trend_rate_mm_per_hour`) that already backs the real score's
       trend factor today — same window, same query, same data.
    2. When that rate is genuinely rising (> 0), linearly extrapolate the
       latest observed water level forward to each requested horizon and
       re-run the exact same rainfall/hydrology/environmental normalizers
       `compute_risk` uses, fed that projected level, combined by the exact
       same `_combine_factors` step — a trajectory point can never diverge
       from how the real score is computed.
    3. The trend factor's own value is held fixed at its current observed
       reading at every horizon rather than re-derived per horizon: it
       already represents "the water is rising at this rate right now",
       which is precisely the fact being extrapolated — recomputing it per
       horizon would double-count the same signal. Rainfall and soil
       moisture are likewise held at their last observed values: this
       feature has no rainfall forecast input, so it never fabricates one.
    4. A flat/falling or insufficient trend produces a flat trajectory
       (every horizon repeats the current score) — "no basis to predict a
       rise" is the honest output, never a fabricated one.
    """
    now = now or datetime.now(timezone.utc)
    config = _get_risk_engine_settings(db)
    weights = config["weights"]
    thresholds = config["thresholds"]

    current = compute_risk(db, now, city_id=city_id)
    raw_rate = _trend_rate_mm_per_hour(db, now, city_id)
    latest_level = _latest_water_level_mm(db, city_id)

    if raw_rate is None or latest_level is None:
        basis = "insufficient_data"
    elif raw_rate <= 0:
        basis = "flat_or_falling"
    else:
        basis = "rising_trend"
    effective_rate = raw_rate if (raw_rate is not None and raw_rate > 0) else 0.0

    # Held fixed across every horizon — see point 3 in the docstring above.
    trend_value = _normalize_trend(db, now, city_id=city_id)

    points: list[TrajectoryPoint] = []
    for hours_ahead in horizons_hours:
        projected_at = now + timedelta(hours=hours_ahead)

        if latest_level is None or latest_level <= 0 or effective_rate == 0.0:
            points.append(
                TrajectoryPoint(
                    hours_ahead=hours_ahead,
                    projected_at=projected_at,
                    score=current.score,
                    severity=current.severity,
                    projected_water_level_mm=(round(latest_level, 1) if latest_level is not None else None),
                )
            )
            continue

        projected_level = latest_level + effective_rate * hours_ahead
        level_multiplier = projected_level / latest_level
        raw_values: dict[str, float | None] = {
            "rainfall": _normalize_rainfall(db, now, city_id=city_id),
            "hydrology": _normalize_hydrology(db, now, multiplier=level_multiplier, city_id=city_id),
            "environmental": _normalize_environmental(db, city_id=city_id),
            "trend": trend_value,
        }
        result = _combine_factors(raw_values, weights, thresholds, now)
        points.append(
            TrajectoryPoint(
                hours_ahead=hours_ahead,
                projected_at=projected_at,
                score=result.score,
                severity=result.severity,
                projected_water_level_mm=round(projected_level, 1),
            )
        )

    return RiskTrajectory(
        current=current,
        points=points,
        trend_rate_mm_per_hour=(round(raw_rate, 2) if raw_rate is not None else None),
        basis=basis,
    )


def describe_warning_outcome(result: RiskResult) -> dict:
    """Non-persisting preview of what `evaluate_and_persist_warnings` would
    do for this `RiskResult`, without touching the database. Used
    exclusively by the P4 Scenario Simulator: a hypothetical projection must
    never create, update or resolve a real `Warning` row — that would
    corrupt the real operational warning lifecycle with a "what if" input.
    Reuses the same `OPEN_SEVERITIES`/`_build_message` the real lifecycle
    uses, so the preview text matches exactly what a real warning would say
    if this projection ever became reality."""
    would_trigger = result.severity in OPEN_SEVERITIES
    return {
        "would_trigger": would_trigger,
        "severity": result.severity if would_trigger else None,
        "message": _build_message(result) if would_trigger else None,
    }


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
