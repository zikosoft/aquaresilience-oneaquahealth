"""Hour-by-hour replay of the Risk Engine and baselines, scored against floods.

Causality: the score at hour t uses only readings observed at or before t.
Factor arithmetic comes from the platform's own module
(`app.services.risk_factors`); only the gathering of inputs is done here.

Replay rules (documented in the protocol):
- hydrology and trend need a water reading in the last 6 h, else they are
  unavailable; unavailable factors are dropped and the remaining weights
  renormalised, exactly as `risk_engine._combine_factors` does;
- an alert is a run of hours with signal >= threshold; runs < 24 h apart merge;
- an event at level L is detected if an alert hour falls in the 72 h up to
  its first crossing of L; lead time = crossing - first alert hour in that
  window;
- an alert is false if no crossing of L falls in [start, end + 72 h] and it
  does not overlap a flood of level L already under way.

Models
  V0    engine as shipped (weights 0.3/0.3/0.2/0.2, fixed references)
  V2a   V0 with hydrology placed between the calibration median and 99.9th
        percentile of the station's own level (instead of trailing 90-day min/max)
  V2ab  V2a with the trend scaled by the calibration 99th percentile of positive
        6-h rises (instead of the fixed 50 mm/h)
  V2c   V2ab with rainfall averaged over the upstream basin (Toulouse only)
  B1    water level alone, B2 6-h rise alone, B3 24-h city rain alone,
  B3c   24-h upstream-basin rain alone (Toulouse only)

Operating point: each model's threshold is the lowest one whose false-alarm
rate on the calibration period is at most TARGET_FA_PER_YEAR. Test-period
detection and lead time are then compared at that matched false-alarm budget,
including the per-event lead-time difference against B1 (paired).

V0 is also reported at the platform's fixed thresholds A = 25 / 50 / 75.

Output: results/metrics_<station>.csv, results/paired_<station>.csv,
results/signals_<station>.parquet
Run: python -m replay
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.services.risk_factors import (
    HYDROLOGY_LOOKBACK_DAYS,
    TREND_WINDOW_HOURS,
    environmental_factor,
    hydrology_factor,
    rainfall_factor,
    trend_factor,
)
from loaders.common import CLEAN, ROOT, log

RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
EVENTS = ROOT / "data" / "events"

DEFAULT_WEIGHTS = {"rainfall": 0.3, "hydrology": 0.3, "environmental": 0.2, "trend": 0.2}
FACTORS = ("rainfall", "hydrology", "environmental", "trend")
MAX_STALENESS = pd.Timedelta(hours=6)
MERGE_GAP = pd.Timedelta(hours=24)
WINDOW = pd.Timedelta(hours=72)
TARGET_FA_PER_YEAR = 1.0
N_BOOT = 2000
SEED = 20261127
HOUR = 3600.0
YEAR = 365.25 * 86400.0

STATIONS = {
    "toulouse_pontneuf": {"level": ("toulouse_pontneuf_H", "h_mm_last"), "weather": "weather_toulouse_H",
                          "basin": "weather_toulouse_basin_H",
                          "calib_end": "2009-12-31 23:00", "test_start": "2010-01-01"},
    "oslo_alna": {"level": ("oslo_alna_H", "h_mm"), "weather": "weather_oslo_H", "basin": None,
                  "calib_end": "2012-12-31 23:00", "test_start": "2013-01-01"},
    "oslo_akerselva": {"level": ("oslo_akerselva_H", "h_mm"), "weather": "weather_oslo_H", "basin": None,
                       "calib_end": "2012-12-31 23:00", "test_start": "2013-01-01"},
}


# ----------------------------------------------------------------- inputs

def _naive(obj):
    """All replay times are naive UTC, so numpy comparisons stay consistent."""
    obj = obj.copy()
    obj.index = pd.DatetimeIndex(obj.index).tz_convert("UTC").tz_localize(None)
    return obj


def _opt(x) -> float | None:
    return None if x is None or np.isnan(x) else float(x)


def build_inputs(level: pd.Series, weather: pd.DataFrame, basin: pd.DataFrame | None) -> pd.DataFrame:
    """Causal inputs on a complete hourly grid."""
    start = max(level.index.min(), weather.index.min())
    end = min(level.index.max(), weather.index.max())
    grid = pd.date_range(start, end, freq="h")
    lvl = level.reindex(grid)
    obs_time = pd.Series(grid.where(lvl.notna()), index=grid).ffill()
    df = pd.DataFrame(index=grid)
    df["level_now"] = lvl
    df["level_latest"] = lvl.ffill()
    df["level_age"] = grid - pd.DatetimeIndex(obs_time)
    df["level_min90"] = lvl.rolling(f"{HYDROLOGY_LOOKBACK_DAYS}D", closed="both").min()
    df["level_max90"] = lvl.rolling(f"{HYDROLOGY_LOOKBACK_DAYS}D", closed="both").max()
    df["trend_first"] = lvl.shift(TREND_WINDOW_HOURS)
    df["rain24"] = weather["precip_mm"].reindex(grid).rolling("24h", closed="right").sum()
    df["soil"] = weather["soil_moisture_ratio"].reindex(grid).ffill()
    if basin is not None:
        df["rain24_basin"] = basin["precip_mm"].reindex(grid).rolling("24h", closed="right").sum()
    return df


def factor_table(df: pd.DataFrame) -> pd.DataFrame:
    fresh = (df["level_age"] <= MAX_STALENESS).to_numpy()
    t_now = df.index.to_pydatetime()
    t_first = (df.index - pd.Timedelta(hours=TREND_WINDOW_HOURS)).to_pydatetime()
    latest, lo, hi = (df[c].to_numpy() for c in ("level_latest", "level_min90", "level_max90"))
    first, now = df["trend_first"].to_numpy(), df["level_now"].to_numpy()
    hyd, trd = [], []
    for i in range(len(df)):
        hyd.append(hydrology_factor(float(latest[i]), float(lo[i]), float(hi[i]))
                   if fresh[i] and not np.isnan(lo[i]) else None)
        trd.append(trend_factor(float(first[i]), t_first[i], float(now[i]), t_now[i])
                   if not (np.isnan(first[i]) or np.isnan(now[i])) else None)
    return pd.DataFrame({
        "rainfall": [rainfall_factor(_opt(x)) for x in df["rain24"].to_numpy()],
        "hydrology": hyd,
        "environmental": [environmental_factor(_opt(x)) for x in df["soil"].to_numpy()],
        "trend": trd,
    }, index=df.index, dtype="float64")


def combine(factors: pd.DataFrame, weights: dict) -> pd.Series:
    """Same weighted mean with renormalisation as risk_engine._combine_factors."""
    w = pd.Series(weights)[list(FACTORS)]
    avail = factors[list(FACTORS)].notna()
    wsum = (avail * w).sum(axis=1)
    num = (factors[list(FACTORS)].fillna(0.0) * w).sum(axis=1)
    return (num / wsum.replace(0, np.nan) * 100.0).clip(0, 100).round(1)


def build_signals(inputs: pd.DataFrame, calib_end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    factors = factor_table(inputs)
    calib = (inputs.index <= calib_end)
    fresh = (inputs["level_age"] <= MAX_STALENESS).to_numpy()
    rise = (inputs["level_now"] - inputs["trend_first"]) / TREND_WINDOW_HOURS

    sig = pd.DataFrame(index=inputs.index)
    sig["V0"] = combine(factors, DEFAULT_WEIGHTS)

    lo = float(inputs.loc[calib, "level_now"].quantile(0.5))
    hi = float(inputs.loc[calib, "level_now"].quantile(0.999))
    f_a = factors.copy()
    f_a["hydrology"] = pd.Series([hydrology_factor(float(x), lo, hi) if ok and not np.isnan(x) else None
                                  for x, ok in zip(inputs["level_latest"].to_numpy(), fresh)],
                                 index=inputs.index, dtype="float64")
    sig["V2a"] = combine(f_a, DEFAULT_WEIGHTS)

    ref = float(rise[calib & (rise > 0).to_numpy()].quantile(0.99))
    f_ab = f_a.copy()
    f_ab["trend"] = (rise / ref).clip(0, 1)
    sig["V2ab"] = combine(f_ab, DEFAULT_WEIGHTS)

    bounds = {"hydrology_lo_mm": round(lo, 1), "hydrology_hi_mm": round(hi, 1),
              "trend_ref_mm_per_h": round(ref, 2)}
    if "rain24_basin" in inputs:
        f_c = f_ab.copy()
        f_c["rainfall"] = pd.Series([rainfall_factor(_opt(x)) for x in inputs["rain24_basin"].to_numpy()],
                                    index=inputs.index, dtype="float64")
        sig["V2c"] = combine(f_c, DEFAULT_WEIGHTS)

    sig["B1"] = inputs["level_latest"].where(inputs["level_age"] <= MAX_STALENESS)
    sig["B2"] = rise
    sig["B3"] = inputs["rain24"]
    if "rain24_basin" in inputs:
        sig["B3c"] = inputs["rain24_basin"]
    return sig, factors, bounds


# ----------------------------------------------------------------- scoring

def episodes(alert: pd.Series) -> pd.DataFrame:
    on = alert[alert]
    if on.empty:
        return pd.DataFrame({"start": pd.Series(dtype="datetime64[ns]"),
                             "end": pd.Series(dtype="datetime64[ns]")})
    new = on.index.to_series().diff() > MERGE_GAP
    g = on.index.to_series().groupby(new.cumsum().values)
    return pd.DataFrame({"start": g.min(), "end": g.max()}).reset_index(drop=True)


def evaluate(alert: pd.Series, events: pd.DataFrame, level: str, start, end) -> dict:
    """Leads per event (None if missed) and false alarms, within [start, end]."""
    col = f"t_cross_{level}"
    lev = events[events[col].notna()]
    ev = lev[(lev[col] >= start) & (lev[col] <= end)]
    on_idx = alert[alert].index
    leads = {}
    for tc in ev[col]:
        in_win = on_idx[(on_idx >= tc - WINDOW) & (on_idx <= tc)]
        leads[tc] = (tc - in_win.min()).total_seconds() / HOUR if len(in_win) else None
    ep = episodes(alert)
    ep = ep[(ep["start"] >= start) & (ep["start"] <= end)]
    crossings = ev[col].to_numpy()
    spans = lev[["start", "end"]].to_numpy()
    false_starts = []
    for s, e in ep[["start", "end"]].to_numpy():
        followed = ((crossings >= s) & (crossings <= e + WINDOW.to_timedelta64())).any()
        overlaps = bool(((spans[:, 0] <= e) & (spans[:, 1] >= s)).any()) if len(spans) else False
        if not (followed or overlaps):
            false_starts.append(pd.Timestamp(s))
    years = (end - start).total_seconds() / YEAR
    period = alert[(alert.index >= start) & (alert.index <= end)]
    return {"leads": leads, "false_starts": false_starts, "alerts": len(ep), "years": years,
            "time_in_alert_pct": round(100 * float(period.mean()), 2) if len(period) else np.nan}


def threshold_for_budget(signal: pd.Series, events, level, start, end, grid) -> float:
    """Lowest threshold whose calibration false-alarm rate is within budget."""
    for a in sorted(grid):
        r = evaluate(signal >= a, events, level, start, end)
        if len(r["false_starts"]) / r["years"] <= TARGET_FA_PER_YEAR:
            return float(a)
    return float(max(grid))


def summarise(r: dict, start, end) -> dict:
    leads = [v for v in r["leads"].values() if v is not None]
    hits, n = len(leads), len(r["leads"])
    fa = len(r["false_starts"])
    out = {"events": n, "hits": hits, "false_alarms": fa, "fa_per_year": round(fa / r["years"], 2),
           "POD": hits / n if n else np.nan,
           "FAR": fa / (hits + fa) if hits + fa else np.nan,
           "CSI": hits / (n + fa) if n + fa else np.nan,
           "lead_median_h": float(np.median(leads)) if leads else np.nan,
           "lead_q1_h": float(np.percentile(leads, 25)) if leads else np.nan,
           "lead_q3_h": float(np.percentile(leads, 75)) if leads else np.nan,
           "time_in_alert_pct": r["time_in_alert_pct"]}
    out.update(_bootstrap(r, start.year, end.year))
    return out


def _bootstrap(r: dict, y0: int, y1: int) -> dict:
    """Year-block bootstrap of POD and CSI."""
    rng = np.random.default_rng(SEED)
    years = np.arange(y0, y1 + 1)
    h = pd.Series([t.year for t, v in r["leads"].items() if v is not None], dtype="int64").value_counts()
    m = pd.Series([t.year for t, v in r["leads"].items() if v is None], dtype="int64").value_counts()
    f = pd.Series([t.year for t in r["false_starts"]], dtype="int64").value_counts()
    h, m, f = (x.reindex(years, fill_value=0).to_numpy() for x in (h, m, f))
    pod, csi = [], []
    for _ in range(N_BOOT):
        i = rng.integers(0, len(years), len(years))
        hh, mm, ff = h[i].sum(), m[i].sum(), f[i].sum()
        if hh + mm:
            pod.append(hh / (hh + mm))
        if hh + mm + ff:
            csi.append(hh / (hh + mm + ff))

    def ci(v):
        return f"[{np.percentile(v, 2.5):.2f}, {np.percentile(v, 97.5):.2f}]" if v else ""

    return {"POD_ci": ci(pod), "CSI_ci": ci(csi)}


def paired_vs(ref: dict, other: dict) -> dict:
    """Per-event lead difference (other - ref) over events both detected."""
    common = [t for t in ref if ref[t] is not None and other.get(t) is not None]
    d = [other[t] - ref[t] for t in common]
    return {"both_detected": len(common),
            "dlead_median_h": float(np.median(d)) if d else np.nan,
            "earlier_than_B1": int(sum(x > 0 for x in d)),
            "later_than_B1": int(sum(x < 0 for x in d)),
            "detected_only_by_model": sum(1 for t in ref if ref[t] is None and other.get(t) is not None),
            "detected_only_by_B1": sum(1 for t in ref if ref[t] is not None and other.get(t) is None)}


# ----------------------------------------------------------------- main

def run_station(name: str, cfg: dict) -> None:
    log(f"Replay: {name}")
    file, col = cfg["level"]
    level = _naive(pd.read_parquet(CLEAN / f"{file}.parquet")[col].dropna())
    weather = _naive(pd.read_parquet(CLEAN / f"{cfg['weather']}.parquet"))
    basin = None
    if cfg["basin"] and (CLEAN / f"{cfg['basin']}.parquet").exists():
        basin = _naive(pd.read_parquet(CLEAN / f"{cfg['basin']}.parquet"))
    elif cfg["basin"]:
        log("    basin rainfall file missing: V2c and B3c skipped")
    events = pd.read_csv(EVENTS / f"events_{name}.csv")
    for c in ("start", "end", "t_cross_S1", "t_cross_S2", "t_cross_S3"):
        events[c] = pd.to_datetime(events[c], utc=True).dt.tz_convert(None)

    inputs = build_inputs(level, weather, basin)
    c0, c1 = inputs.index.min(), pd.Timestamp(cfg["calib_end"])
    t0, t1 = pd.Timestamp(cfg["test_start"]), inputs.index.max()
    sig, factors, bounds = build_signals(inputs, c1)
    pd.concat([sig, factors.add_prefix("f_")], axis=1).to_parquet(RESULTS / f"signals_{name}.parquet")
    log(f"    calibration bounds: {json.dumps(bounds)}")

    rows, paired = [], []
    for lvl in ("S1", "S2"):
        for a in (25.0, 50.0, 75.0):
            r = evaluate(sig["V0"] >= a, events, lvl, t0, t1)
            rows.append({"level": lvl, "model": f"V0 fixed A={a:.0f}", "threshold": a, **summarise(r, t0, t1)})
        leads = {}
        for model in sig.columns:
            s = sig[model]
            cal = s[(s.index >= c0) & (s.index <= c1)].dropna()
            grid = np.arange(10, 97.5, 2.5) if model.startswith("V") \
                else np.unique(np.quantile(cal, np.linspace(0.90, 0.9999, 80)))
            a = threshold_for_budget(s, events, lvl, c0, c1, grid)
            r = evaluate(s >= a, events, lvl, t0, t1)
            leads[model] = r["leads"]
            rows.append({"level": lvl, "model": model, "threshold": round(a, 2), **summarise(r, t0, t1)})
        for model in sig.columns:
            if model != "B1":
                paired.append({"level": lvl, "model": model, **paired_vs(leads["B1"], leads[model])})

    res = pd.DataFrame(rows)
    res.to_csv(RESULTS / f"metrics_{name}.csv", index=False)
    pr = pd.DataFrame(paired)
    pr.to_csv(RESULTS / f"paired_{name}.csv", index=False)

    view = res[res["model"] != "V0 fixed A=50"].copy()
    view["det"] = view["hits"].astype(str) + "/" + view["events"].astype(str)
    view = view.merge(pr[["level", "model", "dlead_median_h", "earlier_than_B1", "later_than_B1"]],
                      on=["level", "model"], how="left")
    with pd.option_context("display.width", 200, "display.precision", 2):
        print(view[["level", "model", "threshold", "det", "fa_per_year", "POD_ci", "lead_median_h",
                    "dlead_median_h", "earlier_than_B1", "later_than_B1"]].to_string(index=False))


def run() -> None:
    for name, cfg in STATIONS.items():
        run_station(name, cfg)


if __name__ == "__main__":
    run()
