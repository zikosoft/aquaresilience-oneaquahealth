"""Pure factor normalizers of the deterministic Risk Engine.

No database and no clock: each function maps inputs that the caller has
already gathered to a 0..1 factor value, or None when the input is not
enough to place it. `risk_engine` uses them for live scoring and the
research backtest harness uses them for historical replay, so both always
run exactly the same arithmetic.
"""
from __future__ import annotations

from datetime import datetime

RAINFALL_REFERENCE_MM_24H = 40.0
TREND_REFERENCE_MM_PER_HOUR = 50.0
TREND_WINDOW_HOURS = 6
HYDROLOGY_LOOKBACK_DAYS = 90


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def rainfall_factor(total_24h_mm: float | None, multiplier: float = 1.0) -> float | None:
    """24h cumulative precipitation against the 40 mm/24h reference."""
    if total_24h_mm is None:
        return None
    adjusted = max(0.0, total_24h_mm * multiplier)
    return _clamp01(adjusted / RAINFALL_REFERENCE_MM_24H)


def hydrology_factor(
    latest_mm: float | None,
    window_min_mm: float | None,
    window_max_mm: float | None,
    multiplier: float = 1.0,
) -> float | None:
    """Latest water level placed within the trailing window's own min/max."""
    if latest_mm is None:
        return None
    if window_min_mm is None or window_max_mm is None or window_max_mm <= window_min_mm:
        return None
    adjusted = max(0.0, latest_mm * multiplier)
    return _clamp01((adjusted - window_min_mm) / (window_max_mm - window_min_mm))


def environmental_factor(soil_moisture_ratio: float | None) -> float | None:
    """Soil moisture ratio, already expressed 0..1 by the provider."""
    if soil_moisture_ratio is None:
        return None
    return _clamp01(soil_moisture_ratio)


def trend_rate_mm_per_hour(
    first_value: float, first_ts: datetime, last_value: float, last_ts: datetime
) -> float | None:
    """Raw, unclamped rate of change between two readings, in mm/h."""
    hours_elapsed = (last_ts - first_ts).total_seconds() / 3600.0
    if hours_elapsed <= 0:
        return None
    return (last_value - first_value) / hours_elapsed


def trend_factor(
    first_value: float,
    first_ts: datetime,
    last_value: float,
    last_ts: datetime,
    level_multiplier: float = 1.0,
) -> float | None:
    """Rate of rise against the 50 mm/h reference; a fall contributes 0."""
    adjusted_last = max(0.0, last_value * level_multiplier)
    rate = trend_rate_mm_per_hour(first_value, first_ts, adjusted_last, last_ts)
    if rate is None:
        return None
    return _clamp01(rate / TREND_REFERENCE_MM_PER_HOUR)
